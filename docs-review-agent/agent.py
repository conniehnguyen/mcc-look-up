"""
Documentation Review Agent
===========================
Reviews a documentation repo against the Microsoft Writing Style Guide.

Features:
  1. Microsoft style guide checks (pattern-based + AI-powered)
  2. Fix suggestions for every finding
  3. Exemption system — mark findings as exempt with a reason
  4. Typo detection
  5. Broken link detection (HTTP and relative)
  6. Code block formatting checks

Usage:
  python3 agent.py /path/to/docs              ← review all docs
  python3 agent.py /path/to/docs --no-ai      ← skip AI analysis (faster)
  python3 agent.py /path/to/docs --no-links   ← skip link checks (faster)
  python3 agent.py --list-exemptions          ← show saved exemptions
  python3 agent.py --remove-exempt ID         ← remove an exemption
"""

import argparse
import os
import re
import sys
import ollama

from checks import check_style_rules, check_headings, check_typos, check_links, check_code_blocks
from exemptions import load_exemptions, save_exemptions, add_exemption, remove_exemption, list_exemptions, is_exempt
from prompts import SYSTEM_PROMPT

MODEL = 'qwen2.5-coder:7b'
DOC_EXTENSIONS = {'.md', '.mdx', '.rst', '.txt'}
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'dist'}

SEVERITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
SEVERITY_ICONS = {'HIGH': '🔴', 'MEDIUM': '🟡', 'LOW': '🔵'}


# ── File discovery ─────────────────────────────────────────────────────────────

def collect_doc_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if any(f.endswith(ext) for ext in DOC_EXTENSIONS):
                found.append(os.path.join(root, f))
    return sorted(found)


# ── Display helpers ────────────────────────────────────────────────────────────

def print_header(text: str):
    print(f'\n{"═"*64}')
    print(f'  {text}')
    print(f'{"═"*64}')


def print_section(text: str):
    print(f'\n{"─"*64}')
    print(f'  {text}')
    print(f'{"─"*64}')


def print_finding(f: dict, exempt: bool = False):
    icon = SEVERITY_ICONS.get(f['severity'], '⚪')
    status = ' [EXEMPT]' if exempt else ''
    print(f'\n  {icon} [{f["severity"]}] {f["category"].upper()}{status}  |  ID: {f["id"]}')
    print(f'  Rule: {f["rule"]}  |  Line {f["line"]}')
    if f['line_text']:
        print(f'  Found: {f["line_text"][:100]}')
    print(f'  Issue: {f["message"]}')
    print(f'  Fix:   {f["fix"]}')


# ── AI analysis ────────────────────────────────────────────────────────────────

def run_ai_analysis(file_path: str, content: str) -> list[dict]:
    """Ask the model to find style issues that patterns can't catch."""
    findings = []
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': f'Review this documentation file: {file_path}\n\n```\n{content[:6000]}\n```'},
            ]
        )
        text = response.message.content or ''
        if 'NO_AI_FINDINGS' in text:
            return []

        # Parse structured findings from model output
        blocks = re.split(r'\n(?=FINDING\s*\|)', text)
        for block in blocks:
            header = re.match(r'FINDING\s*\|\s*LINE\s*(\d+)\s*\|\s*(HIGH|MEDIUM|LOW)', block, re.IGNORECASE)
            if not header:
                continue
            line_num = int(header.group(1))
            severity = header.group(2).upper()
            issue_m = re.search(r'Issue:\s*(.+)', block)
            fix_m = re.search(r'Fix:\s*(.+)', block)
            issue = issue_m.group(1).strip() if issue_m else 'Style issue detected by AI.'
            fix = fix_m.group(1).strip() if fix_m else 'Review and rewrite per Microsoft Style Guide.'

            from checks import make_id
            fid = make_id(file_path, line_num, f'AI-{severity}')
            findings.append({
                'id': fid,
                'file': file_path,
                'line': line_num,
                'rule': 'AI',
                'severity': severity,
                'category': 'style (AI)',
                'message': issue,
                'fix': fix,
                'line_text': '',
            })
    except Exception as e:
        print(f'  ⚠ AI analysis failed for {file_path}: {e}')
    return findings


# ── Main review ────────────────────────────────────────────────────────────────

def review(target_path: str, use_ai: bool, check_links_flag: bool, exemptions: dict) -> list[dict]:
    doc_files = collect_doc_files(target_path)
    if not doc_files:
        print(f'No documentation files found at: {target_path}')
        return []

    print_header(f'Documentation Review Agent')
    print(f'\n  Target: {target_path}')
    print(f'  Files:  {len(doc_files)}')
    print(f'  Model:  {MODEL if use_ai else "none (--no-ai)"}')

    all_findings = []

    for file_path in doc_files:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        print_section(f'📄 {file_path}')

        file_findings = []

        # 1. Style rule pattern checks
        file_findings += check_style_rules(file_path, content)
        file_findings += check_headings(file_path, content)

        # 2. Typo checks
        file_findings += check_typos(file_path, content)

        # 3. Code block checks
        file_findings += check_code_blocks(file_path, content)

        # 4. Link checks (optional — slow due to network calls)
        if check_links_flag:
            print('  Checking links...')
            file_findings += check_links(file_path, content, target_path)

        # 5. AI analysis (optional)
        if use_ai and content.strip():
            print('  Running AI analysis...')
            file_findings += run_ai_analysis(file_path, content)

        # Sort by line number, then severity
        file_findings.sort(key=lambda x: (x['line'], SEVERITY_ORDER.get(x['severity'], 9)))

        if not file_findings:
            print('\n  ✅ No issues found.')
        else:
            active = 0
            for f in file_findings:
                exempt = is_exempt(exemptions, f['id'])
                print_finding(f, exempt)
                if not exempt:
                    active += 1
            print(f'\n  → {active} active finding(s), {len(file_findings) - active} exempt')

        all_findings += file_findings

    return all_findings


# ── Summary ────────────────────────────────────────────────────────────────────

def print_summary(all_findings: list[dict], exemptions: dict):
    active = [f for f in all_findings if not is_exempt(exemptions, f['id'])]
    print_header('Summary')
    counts = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for f in active:
        counts[f['severity']] = counts.get(f['severity'], 0) + 1
    total = len(active)
    print(f'\n  Total active findings: {total}')
    for sev, icon in SEVERITY_ICONS.items():
        print(f'  {icon} {sev}: {counts[sev]}')
    exempt_count = len(all_findings) - total
    if exempt_count:
        print(f'\n  ⚪ Exempt: {exempt_count}')


# ── Exemption prompt ───────────────────────────────────────────────────────────

def prompt_exemptions(all_findings: list[dict], exemptions: dict):
    active_ids = {f['id'] for f in all_findings if not is_exempt(exemptions, f['id'])}
    if not active_ids:
        return

    print('\n' + '─'*64)
    print('  Mark findings as exempt')
    print('  Enter finding IDs (comma-separated), or press Enter to skip:')
    try:
        raw = input('  > ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not raw:
        return

    ids_to_exempt = [x.strip() for x in raw.split(',') if x.strip()]
    changed = False
    for fid in ids_to_exempt:
        if fid not in active_ids:
            print(f'  ⚠ ID not found: {fid}')
            continue
        reason = input(f'  Reason for exempting {fid}: ').strip()
        if not reason:
            reason = 'No reason provided'
        add_exemption(exemptions, fid, reason)
        print(f'  ✓ Exempted {fid}')
        changed = True

    if changed:
        save_exemptions(exemptions)
        print('  Exemptions saved to exemptions.json')


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Documentation review agent (Microsoft Style Guide)')
    parser.add_argument('path', nargs='?', default='.', help='Path to doc file or directory')
    parser.add_argument('--no-ai', action='store_true', help='Skip AI analysis')
    parser.add_argument('--no-links', action='store_true', help='Skip link checking')
    parser.add_argument('--list-exemptions', action='store_true', help='List all saved exemptions')
    parser.add_argument('--remove-exempt', metavar='ID', help='Remove an exemption by ID')
    args = parser.parse_args()

    exemptions = load_exemptions()

    if args.list_exemptions:
        list_exemptions(exemptions)
        return

    if args.remove_exempt:
        remove_exemption(exemptions, args.remove_exempt)
        save_exemptions(exemptions)
        print(f'Removed exemption: {args.remove_exempt}')
        return

    all_findings = review(
        target_path=args.path,
        use_ai=not args.no_ai,
        check_links_flag=not args.no_links,
        exemptions=exemptions,
    )

    print_summary(all_findings, exemptions)
    prompt_exemptions(all_findings, exemptions)


if __name__ == '__main__':
    main()
