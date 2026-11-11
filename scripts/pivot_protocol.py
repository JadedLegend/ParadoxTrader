#!/usr/bin/env python3
"""
CLEAN AND PIVOT PROTOCOL — Pivot Script
=========================================
When you hit a persistent error or structural blocker after 2 attempts,
STOP. Do not brute-force. Run this script.

The constraint becomes the direction. Narrow the focus; do not expand it.

Usage:
    python scripts/pivot_protocol.py
"""

import json
from datetime import datetime

TEMPLATE = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "obstacle_description": "<DESCRIBE: what is failing and how many attempts have been made>",
    "obstacle_as_gradient": "<REFRAME: what is this obstacle pointing toward? What is it revealing about the design?>",
    "what_was_tried": ["<attempt 1>", "<attempt 2>"],
    "what_the_obstacle_is_not": "<DESCRIBE: what this is NOT about — rule out the obvious wrong paths>",
    "narrowed_focus": "<DESCRIBE: the tighter, simpler version of the problem>",
    "next_single_step": "<DESCRIBE: the one smallest possible step forward>",
    "expansion_forbidden": True,
    "notes": ""
}

def main():
    print("\n" + "="*60)
    print("  CLEAN AND PIVOT PROTOCOL — Pivot Gate")
    print("="*60)
    print("\nYou have hit a persistent obstacle. STOP brute-forcing.")
    print("The constraint is the direction. Narrow, do not expand.\n")
    print("Complete this template before writing any new code.\n")
    print("-"*60)
    print(json.dumps(TEMPLATE, indent=2))
    print("-"*60)
    print("\nFAIL CLOSED: No completed JSON = not cleared to write new code.\n")

if __name__ == "__main__":
    main()
