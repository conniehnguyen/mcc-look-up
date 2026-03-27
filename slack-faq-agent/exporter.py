"""
Markdown exporter.

Writes FAQ entries to a markdown file suitable for dropping into a doc site.
FAQs are grouped by channel and sorted alphabetically within each group.
"""

import os
from datetime import datetime
from typing import Dict, List


def export_markdown(faqs: List[Dict], output_path: str, site_name: str = '') -> int:
    """
    Write FAQ entries to a markdown file.

    Parameters
    ----------
    faqs : list of FAQ dicts (from faq_generator.generate_faq)
    output_path : path to write the .md file
    site_name : optional site name used in the file header

    Returns the number of FAQ entries written.
    """
    if not faqs:
        print('No FAQ entries to export.')
        return 0

    # Group by channel
    by_channel: Dict[str, List[Dict]] = {}
    for faq in faqs:
        ch = faq['source_channel']
        by_channel.setdefault(ch, []).append(faq)

    # Sort each channel's FAQs alphabetically by question
    for ch in by_channel:
        by_channel[ch].sort(key=lambda f: f['question'].lower())

    lines = _build_markdown(by_channel, site_name)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    total = sum(len(v) for v in by_channel.values())
    print(f'Wrote {total} FAQ entries to {output_path}')
    return total


def _build_markdown(by_channel: Dict[str, List[Dict]], site_name: str) -> List[str]:
    generated = datetime.utcnow().strftime('%Y-%m-%d')
    title = f'{site_name} — ' if site_name else ''
    lines = [
        f'# {title}Frequently Asked Questions',
        '',
        f'*Generated from Slack on {generated}. Review before publishing.*',
        '',
    ]

    # Table of contents
    lines.append('## Contents')
    lines.append('')
    for ch in sorted(by_channel):
        anchor = ch.lower().replace(' ', '-').replace('_', '-')
        count = len(by_channel[ch])
        lines.append(f'- [{ch}](#{anchor}) ({count} {"entry" if count == 1 else "entries"})')
    lines.append('')
    lines.append('---')
    lines.append('')

    # FAQ sections per channel
    for ch in sorted(by_channel):
        lines.append(f'## {ch}')
        lines.append('')
        for faq in by_channel[ch]:
            lines.append(f"### {faq['question']}")
            lines.append('')
            lines.append(faq['answer'])
            lines.append('')
            if faq.get('tags'):
                tag_str = ' '.join(f'`{t}`' for t in faq['tags'])
                lines.append(f'**Tags:** {tag_str}')
                lines.append('')
            lines.append(f'*Source: #{faq["source_channel"]} · {faq["source_date"]}*')
            lines.append('')
            lines.append('---')
            lines.append('')

    return lines
