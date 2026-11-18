"""The owner's settings: the OpenRouter key, each agent's model, the daily budget.

Set from the private dashboard's Settings page and read by the heartbeat.

- The key is write-only. It lives in its own file (mode 0600) and is never
  returned: reads show only whether it is set and its last four characters.
- Every change is an append-only history row (who, when, field, new value).
  OpenRouter rows include the suffix; data and broker rows record only "set" or "cleared".
- Model choices apply from each agent's next wake, the budget from the next
  wake too; nothing here starts or stops a wake.

Storage, under ``directory`` (normally /var/lib/paradoxtrader/settings):
  settings.sqlite3   append-only history; the current value is the latest row
  openrouter.key     the key, mode 0600
  secrets/<slot>     data and broker keys (see SECRET_SLOTS), each mode 0600

The data and broker keys are only stored here and are not used to place orders.
Live Alpaca key IDs (AK...) are rejected; only paper key IDs (PK...) are accepted.
"""
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from uuid import uuid4

from core.usage.pricing import validate_model

AGENTS = ("tempest", "siren", "alchemist", "weaver", "oracle", "shadow", "paradox_hunter")
MODEL_SLOTS = AGENTS + ("witness",)  # The witness's model is used once it writes prose.
KEY_PATTERN = re.compile(r"sk-or-[A-Za-z0-9_-]{20,200}")
MAX_BUDGET_USD = Decimal("100")
# Write-only keys for market data and paper trading, stored for later steps.
_GENERIC = re.compile(r"[\x21-\x7e]{8,512}")  # Printable, no spaces.
SECRET_SLOTS = {
    "alpaca_key_id": re.compile(r"PK[A-Z0-9]{8,40}"),  # Paper keys only (live keys start with AK).
    "alpaca_secret": re.compile(r"[A-Za-z0-9/+=]{20,100}"),
    "public_com": _GENERIC,
    "alphavantage": re.compile(r"[A-Za-z0-9]{8,64}"),
    "fmp": re.compile(r"[A-Za-z0-9]{16,64}"),
    "bigdata": _GENERIC,
}
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class SettingsError(ValueError):
    """A bounded, safe error code; never contains the key."""


def _now():
    return datetime.now(timezone.utc).isoformat()


class _SettingsConnection(sqlite3.Connection):
    """Keep journal preparation, file writes and recovery under one process lock."""
    lock_fd = None

    def close(self):
        try:
            super().close()
        finally:
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None


class OwnerSettings:
    def __init__(self, directory):
        raw = Path(directory)
        if ".." in raw.parts:
            raise SettingsError("invalid_settings_directory")
        self.directory = Path(os.path.abspath(raw))

    # ---- files --------------------------------------------------------------
    def _check(self, path):
        for item in reversed((path, *path.parents)):
            try:
                mode = item.lstat().st_mode
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(mode):
                raise SettingsError("symlink_settings_path")
        return path

    def _ensure_directory(self):
        self._check(self.directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _db(self):
        self._ensure_directory()
        path = self._check(self.directory / "settings.sqlite3")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        lock_path = self._check(self.directory / "settings.lock")
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            conn = sqlite3.connect(path, timeout=30, factory=_SettingsConnection)
        except BaseException:
            os.close(lock_fd)
            raise
        conn.lock_fd = lock_fd
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("""CREATE TABLE IF NOT EXISTS history (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, change_id TEXT NOT NULL,
                changed_at TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL)""")
            conn.execute("CREATE TRIGGER IF NOT EXISTS history_no_update BEFORE UPDATE ON history "
                         "BEGIN SELECT RAISE(ABORT,'append only settings history'); END")
            conn.execute("CREATE TRIGGER IF NOT EXISTS history_no_delete BEFORE DELETE ON history "
                         "BEGIN SELECT RAISE(ABORT,'append only settings history'); END")
            conn.execute("""CREATE TABLE IF NOT EXISTS pending_credentials (
                change_id TEXT NOT NULL, changed_at TEXT NOT NULL,
                field TEXT PRIMARY KEY, value TEXT NOT NULL, digest TEXT)""")
            if "attempted" not in {row["name"] for row in conn.execute("PRAGMA table_info(pending_credentials)")}:
                conn.execute("ALTER TABLE pending_credentials ADD COLUMN attempted INTEGER NOT NULL DEFAULT 0")
            self._recover_credentials(conn)
        except BaseException:
            conn.close()
            raise
        return conn

    @staticmethod
    def _digest(path):
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            return None

    def _recover_credentials(self, conn):
        # Intent contains only metadata and a digest, never the credential itself.
        with conn:
            for operation in conn.execute("SELECT * FROM pending_credentials").fetchall():
                field = operation["field"]
                if operation["attempted"] == 0:
                    conn.execute("DELETE FROM pending_credentials WHERE field=?", (field,))
                    continue
                try:
                    path = (self._key_path() if field == "openrouter_key"
                            else self._secret_path(field.removeprefix("secret.")))
                    digest = self._digest(path)
                except (OSError, SettingsError):
                    # Leave this intent unresolved; other slots can still recover.
                    continue
                if operation["attempted"] and digest == operation["digest"]:
                    conn.execute("INSERT INTO history(change_id,changed_at,field,value) VALUES (?,?,?,?)",
                                 (operation["change_id"], operation["changed_at"], field, operation["value"]))
                conn.execute("DELETE FROM pending_credentials WHERE field=?", (field,))

    def _key_path(self):
        return self._check(self.directory / "openrouter.key")

    # ---- reads --------------------------------------------------------------
    def _latest(self):
        if not (self.directory / "settings.sqlite3").exists():
            return {}
        with closing(self._db()) as conn:
            rows = conn.execute("SELECT field,value FROM history WHERE seq IN "
                                "(SELECT MAX(seq) FROM history GROUP BY field)").fetchall()
        return {row["field"]: json.loads(row["value"]) for row in rows}

    def models(self):
        """Each slot's chosen model, or None where nothing was chosen yet."""
        latest = self._latest()
        return {slot: latest.get(f"model.{slot}") for slot in MODEL_SLOTS}

    def agent_models(self):
        """The seven agents' models, or None unless all seven are chosen."""
        models = self.models()
        return None if any(models[agent] is None for agent in AGENTS) else {a: models[a] for a in AGENTS}

    def daily_budget(self):
        value = self._latest().get("daily_budget_usd")
        return None if value is None else Decimal(value)

    def key(self):
        """The key itself, for the heartbeat only. None when not set."""
        path = self._key_path()
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        return raw if KEY_PATTERN.fullmatch(raw) else None

    def _secret_path(self, slot):
        if slot not in SECRET_SLOTS:
            raise SettingsError("invalid_secret_slot")
        return self._check(self.directory / "secrets" / slot)

    def secret(self, slot):
        """One stored data or broker key, for the service that uses it. None when unset."""
        try:
            raw = self._secret_path(slot).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        return raw if SECRET_SLOTS[slot].fullmatch(raw) else None

    def read(self, *, history_limit=20):
        """What the Settings page shows. Never includes the key."""
        latest = self._latest()
        key = self.key()
        history = []
        if (self.directory / "settings.sqlite3").exists():
            with closing(self._db()) as conn:
                history = [{"changed_at": row["changed_at"], "field": row["field"],
                            "value": json.loads(row["value"])}
                           for row in conn.execute("SELECT changed_at,field,value FROM history "
                                                   "ORDER BY seq DESC LIMIT ?", (history_limit,))]
        secrets = {}
        for slot in SECRET_SLOTS:
            try:
                value = self.secret(slot)
            except (OSError, UnicodeError, SettingsError):
                secrets[slot] = {"set": False, "ends_with": None, "error": "secret_unreadable"}
                continue
            secrets[slot] = {"set": value is not None, "ends_with": value[-4:] if value else None}
        return {"models": {slot: latest.get(f"model.{slot}") for slot in MODEL_SLOTS},
                "daily_budget_usd": latest.get("daily_budget_usd"),
                "key": {"set": key is not None, "ends_with": key[-4:] if key else None},
                "secrets": secrets,
                "history": history}

    # ---- writes -------------------------------------------------------------
    @staticmethod
    def _validate(changes):
        if (not isinstance(changes, dict) or not changes
                or set(changes) - {"models", "daily_budget_usd", "openrouter_key", "secrets"}):
            raise SettingsError("invalid_settings_fields")
        rows = []
        if "models" in changes:
            models = changes["models"]
            if not isinstance(models, dict) or not models or set(models) - set(MODEL_SLOTS):
                raise SettingsError("invalid_model_slots")
            for slot in MODEL_SLOTS:
                if slot in models:
                    try:
                        rows.append((f"model.{slot}", validate_model(models[slot])))
                    except (TypeError, ValueError):
                        raise SettingsError("invalid_model_id") from None
        if "daily_budget_usd" in changes:
            raw = changes["daily_budget_usd"]
            try:
                budget = Decimal(raw) if isinstance(raw, str) else None
            except InvalidOperation:
                budget = None
            if (budget is None or not budget.is_finite() or not Decimal("0") <= budget <= MAX_BUDGET_USD
                    or budget.as_tuple().exponent < -2):
                raise SettingsError("invalid_daily_budget")
            rows.append(("daily_budget_usd", format(budget.quantize(Decimal("0.01")), "f")))
        secrets = {}
        if "secrets" in changes:
            given = changes["secrets"]
            if not isinstance(given, dict) or not given or set(given) - set(SECRET_SLOTS):
                raise SettingsError("invalid_secret_slot")
            for slot, value in given.items():
                if not isinstance(value, str) or (value != "" and not value.strip()):
                    raise SettingsError(f"invalid_secret_{slot}")
                value = value.strip()
                if value and not SECRET_SLOTS[slot].fullmatch(value):
                    # alpaca_key_id: only paper keys (PK...) are accepted.
                    raise SettingsError(f"invalid_secret_{slot}")
                secrets[slot] = value
        key = None
        if "openrouter_key" in changes:
            key = changes["openrouter_key"]
            if not isinstance(key, str) or (key != "" and not KEY_PATTERN.fullmatch(key.strip())):
                raise SettingsError("invalid_openrouter_key")
            key = key.strip()
        return rows, key, secrets

    def _write_private(self, path, value):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self._check(path.parent / f".{path.name}.{uuid4().hex}")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value + "\n")
            os.replace(temporary, path)
        except BaseException as error:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                raise error from cleanup_error
            raise

    def update(self, changes):
        """Replace credentials atomically and journal their intended metadata
        before mutation, so a failed history commit can be recovered on access."""
        rows, key, secrets = self._validate(changes)
        change_id, now = str(uuid4()), _now()
        if secrets:
            self._ensure_directory()
        # Check every destination before the first mutation, including OpenRouter.
        mutations = [(self._secret_path(slot), value, f"secret.{slot}")
                     for slot, value in secrets.items()]
        if key is not None:
            mutations.append((self._key_path(), key, "openrouter_key"))
        with closing(self._db()) as conn:
            def record(field, value):
                conn.execute("INSERT INTO history(change_id,changed_at,field,value) VALUES (?,?,?,?)",
                             (change_id, now, field, json.dumps(value)))

            pending = {row["field"] for row in conn.execute("SELECT field FROM pending_credentials")}
            if pending.intersection(field for _, _, field in mutations):
                raise SettingsError("credential_recovery_pending")
            # Commit intent before touching files. The connection's lock prevents
            # another process from recovering an operation still being applied.
            with conn:
                for path, value, field in mutations:
                    recorded = ("cleared" if value == "" else
                                "set, ends in ..." + value[-4:] if field == "openrouter_key" else "set")
                    digest = hashlib.sha256((value + "\n").encode()).hexdigest() if value else None
                    conn.execute("INSERT INTO pending_credentials (change_id,changed_at,field,value,digest) VALUES (?,?,?,?,?)",
                                 (change_id, now, field, json.dumps(recorded), digest))
            applied = []
            try:
                for path, value, field in mutations:
                    # Persist operation-specific evidence before attempting this
                    # write. Later batch entries must not look completed merely
                    # because their desired value already exists.
                    with conn:
                        conn.execute("UPDATE pending_credentials SET attempted=1 WHERE field=?", (field,))
                    if value == "":
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                        recorded = "cleared"
                    else:
                        self._write_private(path, value)
                        recorded = ("set, ends in ..." + value[-4:]
                                    if field == "openrouter_key" else "set")
                    applied.append((field, recorded))
            except OSError:
                # Preserve the audit trail for mutations already completed.
                for field, value in applied:
                    record(field, value)
                conn.execute("DELETE FROM pending_credentials WHERE change_id=?", (change_id,))
                conn.commit()
                raise
            for field, value in rows + applied:
                record(field, value)
            conn.execute("DELETE FROM pending_credentials WHERE change_id=?", (change_id,))
            conn.commit()
        return self.read()
