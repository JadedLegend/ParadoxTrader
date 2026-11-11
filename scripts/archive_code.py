#!/usr/bin/env python3
"""
CLEAN AND PIVOT PROTOCOL — Archive Script
==========================================
Never delete code. Archive it. Deletion is extraction. Archiving is composting.

Usage:
    python scripts/archive_code.py <path_to_file_or_dir>

The script moves the target to _archive/ with a timestamp suffix.
"""

import sys
import os
import shutil
from datetime import datetime

ARCHIVE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_archive")

def archive(target_path: str):
    if not os.path.exists(target_path):
        print(f"ERROR: Path does not exist: {target_path}")
        sys.exit(1)

    os.makedirs(ARCHIVE_ROOT, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(target_path.rstrip("/\\"))
    archive_name = f"{basename}__{timestamp}"
    dest = os.path.join(ARCHIVE_ROOT, archive_name)

    shutil.move(target_path, dest)
    print(f"\nEnergy returned to the field: [{basename}] archived.")
    print(f"Location: {dest}\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/archive_code.py <path_to_file_or_dir>")
        sys.exit(1)
    archive(sys.argv[1])

if __name__ == "__main__":
    main()
