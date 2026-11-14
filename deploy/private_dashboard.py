"""Private owner dashboard gateway for the VPS.

Serves the built frontend and the read-only rehearsal inspection API
(``api.rehearsal.create_app``) behind owner authentication, bound to loopback.

Boundaries (see README "VPS handoff"):
- Never imports the broad legacy app (``api/app.py``); no scheduler, model call,
  broker access or mutation route exists here. Only GET/HEAD are accepted.
- The operator token stays server-side: the gateway injects it into the
  in-process rehearsal app after owner authentication. Browsers never see it.
- Missing static assets return 404, not an unhandled 500.

Configuration (environment, normally from /etc/paradoxtrader/dashboard.env):
  PARADOX_DASHBOARD_USER            owner login name
  PARADOX_DASHBOARD_PASSWORD_HASH   "pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>"
  LINEAGE_OPERATOR_TOKEN            server-side token for the rehearsal API
  PARADOX_SESSIONS_ROOT             private Sessions root (default /var/lib/paradoxtrader/sessions)
  PARADOX_FRONTEND_DIST             built frontend (default <repo>/frontend/dist)

Generate a password hash with:  python3 deploy/private_dashboard.py hash-password
Run (loopback only):            python3 deploy/private_dashboard.py serve --port 8080
"""
import base64
import binascii
import getpass
import hashlib
import hmac
import os
import secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from starlette.applications import Starlette  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.responses import FileResponse, PlainTextResponse, Response  # noqa: E402
from starlette.routing import Route  # noqa: E402

PBKDF2_ITERATIONS = 390_000
SECURITY_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def hash_password(password, *, salt=None, iterations=PBKDF2_ITERATIONS):
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, encoded):
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, AttributeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


def _check_basic(header, user, password_hash):
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
    except (binascii.Error, UnicodeError):
        return False
    supplied_user, sep, supplied_password = decoded.partition(":")
    if not sep:
        return False
    user_ok = hmac.compare_digest(supplied_user.encode("utf-8"), user.encode("utf-8"))
    password_ok = verify_password(supplied_password, password_hash)
    return user_ok and password_ok


class OwnerGate:
    """ASGI middleware: GET/HEAD only, owner Basic auth, security headers."""

    def __init__(self, app, *, user, password_hash):
        self.app, self.user, self.password_hash = app, user, password_hash

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if scope["method"] not in ("GET", "HEAD"):
            response = PlainTextResponse("method_not_allowed", status_code=405, headers={**SECURITY_HEADERS, "Allow": "GET, HEAD"})
        elif not (self.user and self.password_hash and _check_basic(headers.get("authorization"), self.user, self.password_hash)):
            response = PlainTextResponse("owner_authentication_required", status_code=401,
                                         headers={**SECURITY_HEADERS, "WWW-Authenticate": 'Basic realm="ParadoxTrader", charset="UTF-8"'})
        else:
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    existing = {k.lower() for k, _ in message.get("headers", [])}
                    extra = [(k.lower().encode("latin-1"), v.encode("latin-1"))
                             for k, v in SECURITY_HEADERS.items() if k.lower().encode("latin-1") not in existing]
                    message = {**message, "headers": list(message.get("headers", [])) + extra}
                await send(message)
            return await self.app(scope, receive, send_with_headers)
        await response(scope, receive, send)


class InjectOperatorToken:
    """Replaces any browser-supplied Authorization with the server-side operator token."""

    def __init__(self, app, token):
        self.app, self.header = app, ("Bearer " + token).encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"authorization"]
            headers.append((b"authorization", self.header))
            scope = {**scope, "headers": headers}
        await self.app(scope, receive, send)


def _static_app(dist):
    dist = Path(dist).resolve()
    index = dist / "index.html"

    async def serve(request):
        relative = request.path_params.get("path", "")
        candidate = (dist / relative).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            raise StarletteHTTPException(status_code=404)
        if relative and candidate.is_file():
            return FileResponse(candidate)
        # Asset-looking paths (with an extension, or under assets/) must 404 when missing.
        if relative.startswith("assets/") or "." in relative.rsplit("/", 1)[-1]:
            raise StarletteHTTPException(status_code=404)
        if index.is_file():
            return FileResponse(index)  # client-side routes of the single-page app
        raise StarletteHTTPException(status_code=404)

    return serve


async def _not_found(request, exc):
    status = exc.status_code if isinstance(exc, StarletteHTTPException) else 404
    return PlainTextResponse("not_found" if status == 404 else "error", status_code=status, headers=SECURITY_HEADERS)


async def _unknown_api(request):
    return Response(status_code=404, headers=SECURITY_HEADERS)


class _Dispatch:
    """Send /api/rehearsals and /api/rehearsals/... to the rehearsal app, everything else to the site."""

    PREFIX = "/api/rehearsals"

    def __init__(self, rehearsal, site):
        self.rehearsal, self.site = rehearsal, site

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path == self.PREFIX or path.startswith(self.PREFIX + "/"):
            return await self.rehearsal(scope, receive, send)
        return await self.site(scope, receive, send)


def create_gateway(*, sessions_root, frontend_dist, operator_token, user, password_hash):
    if not operator_token or not operator_token.strip():
        raise ValueError("operator_token_missing")
    if not user or not password_hash:
        raise ValueError("owner_credentials_missing")
    from api.rehearsal import create_app as create_rehearsal_app

    rehearsal = create_rehearsal_app(Path(sessions_root), operator_token=operator_token)
    site = Starlette(
        routes=[
            Route("/api/{rest:path}", _unknown_api, methods=["GET", "HEAD"]),
            Route("/{path:path}", _static_app(frontend_dist), methods=["GET", "HEAD"]),
        ],
        exception_handlers={StarletteHTTPException: _not_found},
    )
    return OwnerGate(_Dispatch(InjectOperatorToken(rehearsal, operator_token), site),
                     user=user, password_hash=password_hash)


def _from_environment():
    return create_gateway(
        sessions_root=os.environ.get("PARADOX_SESSIONS_ROOT", "/var/lib/paradoxtrader/sessions"),
        frontend_dist=os.environ.get("PARADOX_FRONTEND_DIST", str(REPO / "frontend" / "dist")),
        operator_token=os.environ.get("LINEAGE_OPERATOR_TOKEN", ""),
        user=os.environ.get("PARADOX_DASHBOARD_USER", ""),
        password_hash=os.environ.get("PARADOX_DASHBOARD_PASSWORD_HASH", ""),
    )


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8080)
    sub.add_parser("hash-password")
    args = parser.parse_args(argv)
    if args.command == "hash-password":
        first = getpass.getpass("Dashboard password: ")
        if len(first) < 12 or first != getpass.getpass("Repeat: "):
            print("Passwords must match and be at least 12 characters.", file=sys.stderr)
            return 1
        print(hash_password(first))
        return 0
    if not 1024 <= args.port <= 65535:
        raise ValueError("invalid_port")
    import uvicorn

    uvicorn.run(_from_environment(), host="127.0.0.1", port=args.port, log_level="warning",
                access_log=False, server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
