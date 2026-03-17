"""
Microsoft Writing Style Guide rules implemented as regex patterns.

Each rule has:
  code     - unique rule ID (used in finding IDs and exemptions)
  name     - human-readable slug
  pattern  - regex pattern to search for
  severity - HIGH / MEDIUM / LOW
  message  - explanation of why this violates the style guide
  fix      - concrete suggestion to fix it
  scope    - 'prose' (skip inside code blocks) or 'all'
"""

import re

STYLE_RULES = [
    {
        'code': 'MS-001',
        'name': 'avoid-please',
        'pattern': r'\bplease\b',
        'severity': 'MEDIUM',
        'message': 'Avoid "please" in instructions — it adds words without adding meaning.',
        'fix': 'Remove "please" and rewrite as a direct instruction.',
        'scope': 'prose',
    },
    {
        'code': 'MS-002',
        'name': 'avoid-simple-language',
        'pattern': r'\b(simply|just|easy|easily|straightforward|obviously|clearly|of course)\b',
        'severity': 'MEDIUM',
        'message': 'Avoid words that minimize difficulty. What feels easy to you may not be for the reader.',
        'fix': 'Remove the word. Restate the sentence if needed.',
        'scope': 'prose',
    },
    {
        'code': 'MS-003',
        'name': 'use-select-not-click',
        'pattern': r'\bclick(?:ed|ing|s)?\b',
        'severity': 'LOW',
        'message': 'Use "select" instead of "click" — not all users interact with a mouse.',
        'fix': 'Replace "click" with "select".',
        'scope': 'prose',
    },
    {
        'code': 'MS-004',
        'name': 'spell-out-and',
        'pattern': r'\s&\s',
        'severity': 'LOW',
        'message': 'Spell out "and" instead of using "&" in prose.',
        'fix': 'Replace " & " with " and ".',
        'scope': 'prose',
    },
    {
        'code': 'MS-005',
        'name': 'avoid-exclamation',
        'pattern': r'!',
        'severity': 'LOW',
        'message': 'Avoid exclamation points. They can feel unprofessional or condescending.',
        'fix': 'End the sentence with a period.',
        'scope': 'prose',
    },
    {
        'code': 'MS-006',
        'name': 'descriptive-link-text',
        'pattern': r'\[(?:click here|here|this link|this page|learn more|read more)\]',
        'severity': 'HIGH',
        'message': 'Avoid generic link text. Screen readers read links out of context.',
        'fix': 'Use descriptive link text that tells readers where they will go.',
        'scope': 'all',
    },
    {
        'code': 'MS-007',
        'name': 'present-tense',
        'pattern': r'\bwill\s+(?:be\s+)?(?:show|display|appear|update|load|open|close|run|execute|return|output)\b',
        'severity': 'LOW',
        'message': 'Prefer present tense over future tense.',
        'fix': 'Change "will show" → "shows", "will appear" → "appears", etc.',
        'scope': 'prose',
    },
    {
        'code': 'MS-008',
        'name': 'second-person',
        'pattern': r'\bwe\s+(?:recommend|suggest|advise|think|believe|want|need|encourage)\b',
        'severity': 'MEDIUM',
        'message': 'Avoid first-person "we". Address the reader directly with "you".',
        'fix': 'Rewrite as "You should..." or as a direct instruction.',
        'scope': 'prose',
    },
    {
        'code': 'MS-009',
        'name': 'avoid-etc',
        'pattern': r'\betc\.?\b',
        'severity': 'LOW',
        'message': 'Avoid "etc." — it leaves readers uncertain about what is included.',
        'fix': 'List all items explicitly, or write "and similar items".',
        'scope': 'prose',
    },
    {
        'code': 'MS-010',
        'name': 'plain-note-prefix',
        'pattern': r'^(?:Note|Warning|Important|Tip|Caution):\s',
        'severity': 'LOW',
        'message': 'Use a proper callout block instead of a plain "Note:" prefix.',
        'fix': 'Use > **Note:** or a callout format like :::note ... :::',
        'scope': 'prose',
    },
    {
        'code': 'MS-011',
        'name': 'avoid-latin-abbreviations',
        'pattern': r'\b(e\.g\.|i\.e\.|viz\.|cf\.)\b',
        'severity': 'LOW',
        'message': 'Avoid Latin abbreviations. Use plain English equivalents.',
        'fix': 'Replace "e.g." with "for example", "i.e." with "that is".',
        'scope': 'prose',
    },
    {
        'code': 'MS-012',
        'name': 'avoid-passive-be-verb',
        'pattern': r'\b(?:is|are|was|were|be|been|being)\s+\w+ed\b',
        'severity': 'MEDIUM',
        'message': 'Possible passive voice. Microsoft style prefers active voice.',
        'fix': 'Rewrite with an active subject: "The system updates..." instead of "is updated by...".',
        'scope': 'prose',
    },
    {
        'code': 'MS-013',
        'name': 'title-case-heading',
        'pattern': None,   # handled separately in check_headings()
        'severity': 'LOW',
        'message': 'Use sentence case for headings (capitalize first word and proper nouns only).',
        'fix': 'Change "Getting Started With The API" to "Getting started with the API".',
        'scope': 'prose',
    },
    {
        'code': 'MS-014',
        'name': 'avoid-contractions-cannot',
        'pattern': r'\bcannot\b',
        'severity': 'LOW',
        'message': 'Microsoft style encourages contractions for a conversational tone.',
        'fix': 'Replace "cannot" with "can\'t".',
        'scope': 'prose',
    },
]


def is_title_case_violation(heading_text: str) -> bool:
    """
    Returns True if a heading uses Title Case when it should use Sentence case.
    Sentence case: only first word and proper nouns are capitalized.
    We flag headings where 3+ words are capitalized (excluding first word).
    """
    words = heading_text.split()
    if len(words) < 3:
        return False
    # Count words (after the first) that are capitalized and not short prepositions/articles
    skip = {'a', 'an', 'the', 'and', 'or', 'but', 'for', 'nor', 'so', 'yet',
            'at', 'by', 'in', 'of', 'on', 'to', 'up', 'as', 'is', 'it', 'its'}
    capitalized = sum(
        1 for w in words[1:]
        if w[0].isupper() and w.lower() not in skip and len(w) > 1
    )
    return capitalized >= 2
