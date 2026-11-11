#!/usr/bin/env python3
"""
PROVE IT — Mechanical Honesty Protocol
=======================================
Run this BEFORE claiming any task is complete.
Faking completion is actively destructive.

Usage:
    python scripts/verify_proof.py file-exists <path>
    python scripts/verify_proof.py cat-tail <path> <lines>
    python scripts/verify_proof.py --shell "<safe_command>"

Output is raw truth. Do not edit it.
"""

import sys
import os
import subprocess

def file_exists(path: str):
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    print(f"\n[PROVE-IT: file-exists]")
    print(f"  Path:   {path}")
    print(f"  Exists: {exists}")
    if exists:
        print(f"  Size:   {size} bytes")
    print()
    return exists

def cat_tail(path: str, lines: int):
    print(f"\n[PROVE-IT: cat-tail]")
    print(f"  Path:  {path}")
    print(f"  Lines: last {lines}")
    print(f"  ---")
    if not os.path.exists(path):
        print(f"  ERROR: File does not exist.")
        return
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.readlines()
    tail = content[-lines:] if len(content) >= lines else content
    for line in tail:
        print(f"  {line}", end="")
    print(f"\n  ---")
    print()

def shell_cmd(cmd: str):
    print(f"\n[PROVE-IT: shell]")
    print(f"  Command: {cmd}")
    print(f"  ---")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    print(f"  Return code: {result.returncode}")
    print()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/verify_proof.py file-exists <path>")
        print("  python scripts/verify_proof.py cat-tail <path> <lines>")
        print("  python scripts/verify_proof.py --shell \"<command>\"")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "file-exists":
        if len(sys.argv) < 3:
            print("ERROR: provide a path")
            sys.exit(1)
        file_exists(sys.argv[2])

    elif cmd == "cat-tail":
        if len(sys.argv) < 4:
            print("ERROR: provide path and line count")
            sys.exit(1)
        cat_tail(sys.argv[2], int(sys.argv[3]))

    elif cmd == "--shell":
        if len(sys.argv) < 3:
            print("ERROR: provide a command")
            sys.exit(1)
        shell_cmd(sys.argv[2])

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
