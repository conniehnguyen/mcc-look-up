"""
Exemption management.

Exemptions are stored in exemptions.json next to the agent.
Each exemption is keyed by finding ID and stores the reason + date.

Usage:
  python3 agent.py /path/to/docs                      ← review
  python3 agent.py /path/to/docs --exempt a1b2,c3d4   ← mark findings as exempt
  python3 agent.py /path/to/docs --list-exemptions     ← show all exemptions
"""

import json
import os
from datetime import date

EXEMPTIONS_FILE = os.path.join(os.path.dirname(__file__), 'exemptions.json')


def load_exemptions() -> dict:
    if not os.path.exists(EXEMPTIONS_FILE):
        return {}
    try:
        with open(EXEMPTIONS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_exemptions(exemptions: dict):
    with open(EXEMPTIONS_FILE, 'w') as f:
        json.dump(exemptions, f, indent=2)


def is_exempt(exemptions: dict, finding_id: str) -> bool:
    return finding_id in exemptions


def add_exemption(exemptions: dict, finding_id: str, reason: str):
    exemptions[finding_id] = {
        'reason': reason,
        'exempted_at': str(date.today()),
    }


def remove_exemption(exemptions: dict, finding_id: str):
    exemptions.pop(finding_id, None)


def list_exemptions(exemptions: dict):
    if not exemptions:
        print('No exemptions saved.')
        return
    print(f'\n{"─"*60}')
    print('  Current exemptions')
    print(f'{"─"*60}')
    for fid, info in sorted(exemptions.items()):
        print(f'  ID: {fid}')
        print(f'  Reason: {info["reason"]}')
        print(f'  Date:   {info["exempted_at"]}')
        print()
