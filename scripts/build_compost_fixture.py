#!/usr/bin/env python3
"""Project Journals examples from the shared temporary offline session fixture."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_rehearsal_fixture import build_fixture, RUN_ID

OUTPUT = ROOT / 'frontend' / 'src' / 'journals' / 'fixture.json'


def build_compost_fixture():
    source = build_fixture()
    return {key: source[key] for key in ('kind', 'observed_at', 'provenance', 'runs', 'journals', 'witnesses', 'sources')}


def main():
    fixture = build_compost_fixture()
    if '--check' in sys.argv:
        if json.loads(OUTPUT.read_text(encoding='utf-8')) != fixture:
            raise SystemExit('Journals fixture is stale; rebuild from the shared scripted temporary session.')
        print('Journals fixture matches the shared scripted session and preserved compost sources.')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(fixture, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
        print('Generated local Journals examples from actual temporary stores.')


if __name__ == '__main__':
    main()
