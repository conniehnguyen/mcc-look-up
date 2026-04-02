"""
Markdown exporter.

Writes conversation summaries to a markdown file suitable for dropping into a doc site.
Summaries are grouped by channel and sorted alphabetically by title within each group.
"""

import os
from datetime import datetime
from typing import Dict, List

_RESOLVED_LABEL = {
    'yes': 'Resolved',
    'no': 'Unresolved',
    'partial': 'Partially resolved',
    'unknown': '',
}


def export_markdown(faqs: List[Dict], output_path: str, site_name: str = '') -> int:
    """
    Write conversation summaries to a markdown file.

    Parameters
    ----------
    faqs : list of summary dicts (from faq_generator.generate_faq)
    output_path : path to write the .md file
    site_name : optional site name used in the file header

    Returns the number of entries written.
    """
    if not faqs:
        print('No summaries to export.')
        return 0

    # Group by channel
    by_channel: Dict[str, List[Dict]] = {}
    for faq in faqs:
        ch = faq['source_channel']
        by_channel.setdefault(ch, []).append(faq)

    # Sort each channel's entries alphabetically by title
    for ch in by_channel:
        by_channel[ch].sort(key=lambda f: f['title'].lower())

    lines = _build_markdown(by_channel, site_name)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    total = sum(len(v) for v in by_channel.values())
    print(f'Wrote {total} conversation summaries to {output_path}')
    return total


def _build_markdown(by_channel: Dict[str, List[Dict]], site_name: str) -> List[str]:
    generated = datetime.utcnow().strftime('%Y-%m-%d')
    title = f'{site_name} — ' if site_name else ''
    lines = [
        f'# {title}Slack Conversation Summaries',
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
        lines.append(f'- [{ch}](#{anchor}) ({count} {"thread" if count == 1 else "threads"})')
    lines.append('')
    lines.append('---')
    lines.append('')

    # Summary sections per channel
    for ch in sorted(by_channel):
        lines.append(f'## {ch}')
        lines.append('')
        for entry in by_channel[ch]:
            lines.append(f"### {entry['title']}")
            lines.append('')
            lines.append(f"**Q:** {entry['question']}")
            lines.append('')
            lines.append(entry['summary'])
            lines.append('')
            resolved_label = _RESOLVED_LABEL.get(entry.get('resolved', ''), '')
            meta_parts = []
            if resolved_label:
                meta_parts.append(resolved_label)
            if entry.get('tags'):
                tag_str = ' '.join(f'`{t}`' for t in entry['tags'])
                meta_parts.append(f'Tags: {tag_str}')
            if meta_parts:
                lines.append(' · '.join(meta_parts))
                lines.append('')
            lines.append(f'*Source: #{entry["source_channel"]} · {entry["source_date"]}*')
            lines.append('')
            lines.append('---')
            lines.append('')

    return lines
