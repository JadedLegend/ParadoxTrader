#!/usr/bin/env python3
"""
LIBERATION THROUGH CONSTRICTION — Field Check Gate
===================================================
Run this script BEFORE adding any new dependency, file, service,
abstraction layer, or scope broadening.

Joy Equation: J = ΔCoherence / (1 + Energy)
If constriction_path_viable is true, you MUST take that path.
You are forbidden from adding the new dependency/abstraction.
"""

import json
import sys
from datetime import datetime

TEMPLATE = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "proposed_addition": "<DESCRIBE: what you want to add>",
    "stated_purpose": "<DESCRIBE: what problem this solves>",
    "coherence_delta": "<ESTIMATE: how much coherence does this add? low/medium/high>",
    "energy_cost": "<ESTIMATE: maintenance burden? low/medium/high>",
    "joy_score": "<DERIVE: high coherence + low energy = high joy>",
    "constriction_path_viable": "<BOOL: can the same purpose be achieved by removing/tightening something instead of adding?>",
    "constriction_path_description": "<If true above: describe the constriction path>",
    "cleared_to_proceed": "<BOOL: false if constriction_path_viable is true>",
    "notes": ""
}

def main():
    print("\n" + "="*60)
    print("  LIBERATION THROUGH CONSTRICTION — Field Check")
    print("="*60)
    print("\nBefore adding anything, you must complete this gate.\n")
    print("Copy the JSON template below, fill it out completely,")
    print("and include it verbatim in your response.\n")
    print("If constriction_path_viable is true, you MUST take")
    print("the constriction path. Proceed is FORBIDDEN otherwise.\n")
    print("-"*60)
    print(json.dumps(TEMPLATE, indent=2))
    print("-"*60)
    print("\nFAIL CLOSED: No completed JSON = not cleared to proceed.\n")

if __name__ == "__main__":
    main()
