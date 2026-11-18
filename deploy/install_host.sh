#!/bin/bash
# Install a release on the VPS as root. Idempotent. Starts ONLY the read-only
# dashboard and the backup timer. It never starts agents, a scheduler, a model
# session or anything with broker access, and never runs api/app.py.
#
# Usage: sudo deploy/install_host.sh /path/to/paradoxtrader-<sha>.tar.gz
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root." >&2; exit 1; }
TARBALL="${1:?usage: install_host.sh <release.tar.gz>}"
APP_USER=paradoxtrader
BASE=/opt/paradoxtrader
ETC=/etc/paradoxtrader
DATA=/var/lib/paradoxtrader
BACKUPS=/var/backups/paradoxtrader

id "$APP_USER" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin "$APP_USER"
install -d -m 0755 "$BASE" "$BASE/releases"
install -d -m 0750 -o root -g "$APP_USER" "$ETC"
install -d -m 0700 -o "$APP_USER" -g "$APP_USER" "$DATA" "$DATA/sessions" "$DATA/settings"
install -d -m 0700 "$BACKUPS"

# awk reads the whole listing: head -1 would kill tar with SIGPIPE under pipefail.
NAME="$(tar -tzf "$TARBALL" | awk -F/ 'NR == 1 { print $1 }')"
case "$NAME" in paradoxtrader-*) ;; *) echo "Unexpected tarball layout: $NAME" >&2; exit 1;; esac
if [ ! -d "$BASE/releases/$NAME" ]; then
  tar -xzf "$TARBALL" -C "$BASE/releases"
  chown -R root:root "$BASE/releases/$NAME"
fi
REL="$BASE/releases/$NAME"
[ -f "$REL/frontend/dist/index.html" ] || { echo "Release has no built frontend (frontend/dist)." >&2; exit 1; }
[ ! -e "$REL/api/app.py" ] && [ ! -e "$REL/start.sh" ] || { echo "Release contains the legacy app (api/app.py or start.sh); rebuild with deploy/build_release.sh." >&2; exit 1; }

[ -x "$BASE/venv/bin/python" ] || python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install --quiet --upgrade pip
"$BASE/venv/bin/pip" install --quiet -r "$REL/requirements.txt"
ln -sfn "$REL" "$BASE/current"

if [ ! -f "$ETC/dashboard.env" ]; then
  TOKEN="$("$BASE/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  umask 077
  cat > "$ETC/dashboard.env" <<ENV
PARADOX_DASHBOARD_USER=owner
# Set with: $BASE/venv/bin/python $BASE/current/deploy/private_dashboard.py hash-password
PARADOX_DASHBOARD_PASSWORD_HASH=
LINEAGE_OPERATOR_TOKEN=$TOKEN
PARADOX_SESSIONS_ROOT=$DATA/sessions
PARADOX_FRONTEND_DIST=$BASE/current/frontend/dist
ENV
  chown root:"$APP_USER" "$ETC/dashboard.env"
  chmod 0640 "$ETC/dashboard.env"
fi

install -m 0644 "$REL"/deploy/systemd/paradoxtrader-*.service "$REL"/deploy/systemd/paradoxtrader-*.timer \
  "$REL"/deploy/systemd/paradoxtrader-*.path /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now paradoxtrader-backup.timer
# Settings "Check connection": the page leaves a request, this runs the check (no paid replies).
systemctl enable --now paradoxtrader-check.path

if grep -q '^PARADOX_DASHBOARD_PASSWORD_HASH=pbkdf2_sha256' "$ETC/dashboard.env"; then
  systemctl enable paradoxtrader-dashboard.service
  systemctl restart paradoxtrader-dashboard.service
  echo "Dashboard running on 127.0.0.1:8080. Reach it with: ssh -L 8080:127.0.0.1:8080 <user>@<host>"
else
  echo "Dashboard installed but NOT started: set PARADOX_DASHBOARD_PASSWORD_HASH in $ETC/dashboard.env, then rerun."
fi
echo "Installed $NAME. Agents, scheduler and trading remain off."
