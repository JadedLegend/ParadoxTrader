"""Consistent local SQLite backups for the VPS.

Copies every SQLite database under the data roots into a timestamped folder in
the backup directory using SQLite's online backup API (consistent per database;
not one cross-database instant, and not an offsite backup).

Each run stages into ``<backup_dir>/.backup-<stamp>`` and renames it into place
only when every database copied and passed ``PRAGMA integrity_check``. Staging
folders left behind by an interrupted run are removed at the start of the next
run. All SQLite handles are closed explicitly.

Usage:
  python3 deploy/backup_data.py --source /var/lib/paradoxtrader --dest /var/backups/paradoxtrader --keep 14
"""
import argparse
import os
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

SQLITE_SUFFIXES = (".sqlite3", ".sqlite", ".db")
STAGING_PREFIX = ".backup-"
SQLITE_HEADER = b"SQLite format 3\x00"


def is_sqlite(path):
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == SQLITE_HEADER
    except OSError:
        return False


def find_databases(source):
    source = Path(source)
    found = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink() or not path.is_file() or not path.name.endswith(SQLITE_SUFFIXES):
            continue
        if is_sqlite(path):
            found.append(path)
    return found


def cleanup_staging(dest):
    """Remove staging folders left by interrupted runs. Returns the removed paths."""
    removed = []
    dest = Path(dest)
    if not dest.is_dir():
        return removed
    for entry in dest.iterdir():
        if entry.name.startswith(STAGING_PREFIX) and entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
            removed.append(entry)
    return removed


def copy_database(src, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)) as source_conn:
        with closing(sqlite3.connect(str(target))) as target_conn:
            source_conn.backup(target_conn)
    with closing(sqlite3.connect(f"file:{target}?mode=ro", uri=True)) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"integrity_check_failed: {target.name}")


def prune(dest, keep):
    snapshots = sorted(p for p in Path(dest).iterdir()
                       if p.is_dir() and not p.is_symlink() and not p.name.startswith(STAGING_PREFIX))
    removed = []
    for old in snapshots[:-keep] if keep > 0 else []:
        shutil.rmtree(old)
        removed.append(old)
    return removed


def run_backup(source, dest, *, keep=14, now=None):
    source, dest = Path(source), Path(dest)
    if not source.is_dir():
        raise FileNotFoundError(f"source_missing: {source}")
    dest.mkdir(parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    cleaned = cleanup_staging(dest)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    final = dest / stamp
    if final.exists():
        raise FileExistsError(f"snapshot_exists: {final.name}")
    staging = dest / f"{STAGING_PREFIX}{stamp}"
    staging.mkdir(mode=0o700)
    copied = []
    try:
        for db in find_databases(source):
            relative = db.relative_to(source)
            copy_database(db, staging / relative)
            copied.append(str(relative))
        staging.rename(final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    pruned = prune(dest, keep)
    return {"snapshot": str(final), "databases": copied, "cleaned_staging": [p.name for p in cleaned],
            "pruned": [p.name for p in pruned]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Consistent local SQLite backups")
    parser.add_argument("--source", default="/var/lib/paradoxtrader")
    parser.add_argument("--dest", default="/var/backups/paradoxtrader")
    parser.add_argument("--keep", type=int, default=14)
    args = parser.parse_args(argv)
    result = run_backup(args.source, args.dest, keep=args.keep)
    print(f"snapshot={result['snapshot']} databases={len(result['databases'])} "
          f"cleaned_staging={len(result['cleaned_staging'])} pruned={len(result['pruned'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
