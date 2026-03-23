"""
Deterministic checks that don't need an AI model.

  check_style_rules()        — pattern-based Microsoft style guide violations
  check_headings()           — heading sentence case
  check_typos()              — spell checking (skips code blocks and technical terms)
  check_links()              — broken HTTP and relative file links
  check_code_blocks()        — code blocks missing language tags, unclosed fences
  check_sensitive_content()  — credentials, internal infrastructure, version disclosure
"""

import re
import os
import hashlib
import urllib.request
import urllib.error
from typing import List, Dict

from style_rules import STYLE_RULES, is_title_case_violation

# ── Finding helpers ────────────────────────────────────────────────────────────

def make_id(file_path: str, line_num: int, rule_code: str) -> str:
    """Short stable ID for a finding — used for exemptions."""
    key = f"{file_path}:{line_num}:{rule_code}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


def finding(file_path, line_num, rule_code, severity, category, message, fix, line_text=''):
    return {
        'id': make_id(file_path, line_num, rule_code),
        'file': file_path,
        'line': line_num,
        'rule': rule_code,
        'severity': severity,
        'category': category,
        'message': message,
        'fix': fix,
        'line_text': line_text.strip(),
    }


# ── Code block detection ───────────────────────────────────────────────────────

def get_code_block_lines(lines: List[str]) -> set:
    """Return set of line numbers (1-based) that are inside fenced code blocks."""
    in_block = False
    fence_char = ''
    code_lines = set()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not in_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_block = True
                fence_char = stripped[:3]
                code_lines.add(i)
        else:
            code_lines.add(i)
            if stripped == fence_char or stripped.startswith(fence_char) and len(stripped) == 3:
                in_block = False
    return code_lines


# ── Style rule checks ──────────────────────────────────────────────────────────

def check_style_rules(file_path: str, content: str) -> List[Dict]:
    findings = []
    lines = content.splitlines()
    code_lines = get_code_block_lines(lines)

    for rule in STYLE_RULES:
        if rule['pattern'] is None:
            continue  # handled separately
        pattern = re.compile(rule['pattern'], re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if rule['scope'] == 'prose' and i in code_lines:
                continue
            if pattern.search(line):
                findings.append(finding(
                    file_path, i, rule['code'],
                    rule['severity'], 'style',
                    rule['message'], rule['fix'], line
                ))
    return findings


def check_headings(file_path: str, content: str) -> List[Dict]:
    findings = []
    for i, line in enumerate(content.splitlines(), 1):
        m = re.match(r'^#{2,6}\s+(.+)', line)  # skip H1 — document titles are exempt
        if m:
            heading_text = m.group(1).strip()
            if is_title_case_violation(heading_text):
                findings.append(finding(
                    file_path, i, 'MS-013',
                    'LOW', 'style',
                    f'Heading appears to use Title Case: "{heading_text}"',
                    'Use sentence case: capitalize only the first word and proper nouns.',
                    line
                ))
    return findings


# ── Typo checks ────────────────────────────────────────────────────────────────

# Technical terms to ignore
ALLOWED_WORDS = {
    'ollama', 'qwen', 'llama', 'mistral', 'openai', 'anthropic', 'claude',
    'api', 'apis', 'url', 'urls', 'http', 'https', 'sdk', 'cli', 'ui', 'ux',
    'json', 'xml', 'html', 'css', 'sql', 'nosql', 'oauth', 'saml', 'jwt',
    'bool', 'boolean', 'int', 'str', 'async', 'await', 'namespace', 'enum',
    'stdout', 'stderr', 'stdin', 'chmod', 'mkdir', 'sudo', 'npm', 'pip',
    'repo', 'repos', 'frontend', 'backend', 'dropdown', 'checkbox', 'tooltip',
    'navbar', 'sidebar', 'webhook', 'webhooks', 'oauth2', 'localhost',
    'timestamp', 'timestamps', 'boolean', 'booleans', 'runtime', 'runtimes',
    'codebase', 'codebases', 'workaround', 'workarounds', 'plugin', 'plugins',
    'dropdown', 'dropdowns', 'autocomplete', 'autofill', 'prebuilt', 'builtin',
    'config', 'configs', 'env', 'envs', 'uncheck', 'unselect', 'onclick',
    'github', 'gitlab', 'macos', 'linux', 'ios', 'android', 'regex', 'regexes',
}


def check_typos(file_path: str, content: str) -> List[Dict]:
    findings = []
    try:
        from spellchecker import SpellChecker
        spell = SpellChecker()
    except ImportError:
        return []  # graceful fallback if not installed

    lines = content.splitlines()
    code_lines = get_code_block_lines(lines)

    for i, line in enumerate(lines, 1):
        if i in code_lines:
            continue
        # Strip markdown syntax before spell-checking
        clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)   # links
        clean = re.sub(r'`[^`]+`', '', clean)                      # inline code
        clean = re.sub(r'[*_#>|]', ' ', clean)                     # markdown chars
        words_in_line = re.findall(r"[a-zA-Z']{3,}", clean)

        for word in words_in_line:
            lower = word.lower().strip("'")
            if lower in ALLOWED_WORDS:
                continue
            if re.search(r'[A-Z].*[A-Z]', word):
                continue  # skip CamelCase (likely a name or identifier)
            misspelled = spell.unknown([lower])
            if misspelled:
                correction = spell.correction(lower)
                if correction and correction != lower:
                    findings.append(finding(
                        file_path, i, 'TYPO',
                        'MEDIUM', 'typo',
                        f'Possible misspelling: "{word}" → did you mean "{correction}"?',
                        f'Replace "{word}" with "{correction}".',
                        line
                    ))
    return findings


# ── Link checks ────────────────────────────────────────────────────────────────

def _http_check(findings: List[Dict], file_path: str, i: int, url: str, line: str, label: str = ''):
    """Send a HEAD request and append a finding if the URL is broken."""
    display = label or url
    try:
        req = urllib.request.Request(url, method='HEAD',
            headers={'User-Agent': 'Mozilla/5.0 docs-review-agent/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status >= 400:
                findings.append(finding(
                    file_path, i, 'LINK', 'HIGH', 'link',
                    f'Broken link (HTTP {resp.status}): {display}',
                    'Update or remove the broken link.', line
                ))
    except urllib.error.HTTPError as e:
        if e.code >= 400:
            findings.append(finding(
                file_path, i, 'LINK', 'HIGH', 'link',
                f'Broken link (HTTP {e.code}): {display}',
                'Update or remove the broken link.', line
            ))
    except Exception:
        findings.append(finding(
            file_path, i, 'LINK', 'HIGH', 'link',
            f'Unreachable link: {display}',
            'Verify the link is correct and the server is reachable.', line
        ))


def check_links(file_path: str, content: str, base_path: str, base_url: str = '') -> List[Dict]:
    findings = []
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^\)]+)\)')

    for i, line in enumerate(content.splitlines(), 1):
        for m in link_pattern.finditer(line):
            url = m.group(2).strip()

            # Skip anchor-only links and mailto
            if url.startswith('#') or url.startswith('mailto:'):
                continue

            if url.startswith('http://') or url.startswith('https://'):
                # External HTTP link — check directly
                _http_check(findings, file_path, i, url, line)

            elif base_url:
                # Localhost mode: convert every relative/absolute path to a
                # full localhost URL and send an HTTP request.
                url_path = url.split('#')[0]
                if not url_path:
                    continue  # anchor-only after stripping fragment

                if url_path.startswith('/'):
                    # Absolute path — join straight onto the base URL
                    full_url = base_url.rstrip('/') + url_path
                else:
                    # Relative path — resolve to an absolute file path, then
                    # compute its position relative to the repo root so we can
                    # build the correct URL path.
                    doc_dir = os.path.dirname(file_path)
                    resolved = os.path.normpath(os.path.join(doc_dir, url_path))
                    rel = os.path.relpath(resolved, base_path)
                    full_url = base_url.rstrip('/') + '/' + rel.replace(os.sep, '/')

                _http_check(findings, file_path, i, full_url, line, label=url)

            else:
                # Filesystem mode — check whether the target file exists on disk
                url_path = url.split('#')[0]
                if not url_path:
                    continue  # anchor-only link after stripping fragment

                if url_path.startswith('/'):
                    # Absolute path: resolve from repo root (base_path)
                    target = os.path.normpath(os.path.join(base_path, url_path.lstrip('/')))
                else:
                    # Relative path: resolve from this file's directory
                    doc_dir = os.path.dirname(file_path)
                    target = os.path.normpath(os.path.join(doc_dir, url_path))

                # Try appending .md if no extension given and path doesn't exist
                if not os.path.exists(target) and not os.path.splitext(target)[1]:
                    if os.path.exists(target + '.md'):
                        target = target + '.md'

                if not os.path.exists(target):
                    findings.append(finding(
                        file_path, i, 'LINK', 'HIGH', 'link',
                        f'Broken relative link — file not found: {url}',
                        f'Check the path. Expected: {target}', line
                    ))

    return findings


# ── Code block checks ──────────────────────────────────────────────────────────

def check_code_blocks(file_path: str, content: str) -> List[Dict]:
    findings = []
    lines = content.splitlines()
    in_block = False
    block_start = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if not in_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_block = True
                block_start = i
                lang = stripped[3:].strip()
                if not lang:
                    findings.append(finding(
                        file_path, i, 'CODE-001',
                        'LOW', 'code',
                        'Code block is missing a language identifier.',
                        'Add a language after the opening fence, e.g. ```python or ```bash',
                        line
                    ))
        else:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                in_block = False

    # Unclosed fence
    if in_block:
        findings.append(finding(
            file_path, block_start, 'CODE-002',
            'HIGH', 'code',
            f'Unclosed code block starting at line {block_start}.',
            'Add a closing ``` fence.',
            lines[block_start - 1]
        ))

    return findings


# ── Sensitive content checks ────────────────────────────────────────────────────

# Patterns that fire everywhere (including inside code blocks).
# 'scope': 'all'   → checked in prose AND code blocks
# 'scope': 'prose' → skipped inside code blocks (e.g. file paths, version strings
#                    are often intentional in code examples)
SENSITIVE_PATTERNS = [

    # ── Credentials ────────────────────────────────────────────────────────────
    {
        'code': 'SEC-001', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Private key or certificate block',
        'pattern': r'-----BEGIN\s+(?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?(?:PRIVATE KEY|CERTIFICATE)',
        'fix': 'Remove private keys and certificates from documentation entirely.',
    },
    {
        'code': 'SEC-002', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Credentials embedded in URL',
        'pattern': r'https?://[^\s/"]+:[^\s/"@]+@',
        'fix': 'Replace embedded credentials with a placeholder, e.g. https://<user>:<password>@host/',
    },
    {
        'code': 'SEC-003', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Hardcoded secret value',
        # Matches   password: "abc123"   or   API_KEY=abc123
        # Skips     password: <YOUR_KEY>  or   password: ****  (placeholders)
        'pattern': (
            r'(?i)(?:password|passwd|secret|api[-_]?key|auth[-_]?token|'
            r'access[-_]?key|private[-_]?key|client[-_]?secret)\s*[:=]\s*'
            r'["\']?(?!<|your[-_]|example|change[-_]?me|\*+|xxx+|placeholder)'
            r'[A-Za-z0-9+/!@#$%^&*()_\-]{8,}'
        ),
        'fix': 'Replace the value with a placeholder like <YOUR_SECRET> or load from an environment variable.',
    },

    # ── Known API key formats ───────────────────────────────────────────────────
    {
        'code': 'SEC-004', 'severity': 'HIGH', 'scope': 'all',
        'label': 'AWS access key ID',
        'pattern': r'AKIA[0-9A-Z]{16}',
        'fix': 'Revoke this key immediately and remove it from documentation.',
    },
    {
        'code': 'SEC-005', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Google API key',
        'pattern': r'AIza[0-9A-Za-z\-_]{35}',
        'fix': 'Revoke this key immediately and remove it from documentation.',
    },
    {
        'code': 'SEC-006', 'severity': 'HIGH', 'scope': 'all',
        'label': 'GitHub personal access token',
        'pattern': r'gh[pousr]_[A-Za-z0-9]{36,}',
        'fix': 'Revoke this token immediately and remove it from documentation.',
    },
    {
        'code': 'SEC-007', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Slack token',
        'pattern': r'xox[baprs]-[0-9A-Za-z\-]{10,}',
        'fix': 'Revoke this token immediately and remove it from documentation.',
    },
    {
        'code': 'SEC-008', 'severity': 'HIGH', 'scope': 'all',
        'label': 'Stripe live secret key',
        'pattern': r'sk_live_[0-9A-Za-z]{24,}',
        'fix': 'Revoke this key immediately and remove it from documentation.',
    },

    # ── Internal infrastructure ─────────────────────────────────────────────────
    {
        'code': 'SEC-010', 'severity': 'MEDIUM', 'scope': 'all',
        'label': 'Internal RFC 1918 IP address',
        'pattern': (
            r'(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}'
            r'|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}'
            r'|192\.168\.\d{1,3}\.\d{1,3})'
        ),
        'fix': 'Replace internal IP addresses with placeholders like <SERVER_IP> or remove from public docs.',
    },
    {
        'code': 'SEC-011', 'severity': 'MEDIUM', 'scope': 'all',
        'label': 'Staging or dev environment URL',
        'pattern': r'(?i)https?://(?:staging|dev|uat|test|preprod|sandbox)\.',
        'fix': 'Replace staging/dev URLs with production URLs or generic placeholders.',
    },
    {
        'code': 'SEC-012', 'severity': 'MEDIUM', 'scope': 'all',
        'label': 'Internal domain suffix (.internal, .corp, .local)',
        'pattern': r'[\w\-]+\.(?:internal|corp|local|lan|intranet)(?:[/\s"\':]|$)',
        'fix': 'Remove internal domain names from public documentation.',
    },

    # ── Version disclosure ──────────────────────────────────────────────────────
    {
        'code': 'SEC-020', 'severity': 'LOW', 'scope': 'prose',
        'label': 'Specific OS or middleware version disclosed',
        'pattern': (
            r'(?i)(?:running|installed|using|version|v)\s+'
            r'(?:ubuntu|centos|debian|rhel|windows server|apache|nginx|'
            r'mysql|postgres|redis|elasticsearch)\s+[\d.]+'
        ),
        'fix': 'Avoid pinning public docs to exact software versions — use the major version or omit.',
    },

    # ── File system paths ───────────────────────────────────────────────────────
    {
        'code': 'SEC-021', 'severity': 'LOW', 'scope': 'prose',
        'label': 'Internal file system path',
        'pattern': r'(?:/opt/[\w]|/etc/[\w]|/var/[\w]|/home/[\w]+/|C:\\Users\\[\w]+\\)',
        'fix': 'Replace specific file paths with generic placeholders like /path/to/config.',
    },

    # ── Personnel / PII ─────────────────────────────────────────────────────────
    {
        'code': 'SEC-030', 'severity': 'LOW', 'scope': 'all',
        'label': 'Real email address (consider using example.com)',
        # Skips common placeholder domains
        'pattern': r'[a-zA-Z0-9._%+\-]+@(?!example\.com|your\-domain\.com|domain\.com)[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        'fix': 'Replace real email addresses with examples like user@example.com to avoid exposing personnel.',
    },
]


def check_sensitive_content(file_path: str, content: str) -> List[Dict]:
    """
    Scan a documentation file for content that could aid attackers:
    credentials, known API key formats, internal infrastructure references,
    version disclosures, and personally identifiable information.
    """
    findings = []
    lines = content.splitlines()
    code_lines = get_code_block_lines(lines)

    for pattern_def in SENSITIVE_PATTERNS:
        regex = re.compile(pattern_def['pattern'])
        for i, line in enumerate(lines, 1):
            if pattern_def['scope'] == 'prose' and i in code_lines:
                continue  # prose-only patterns skip code blocks
            if regex.search(line):
                findings.append(finding(
                    file_path, i,
                    pattern_def['code'],
                    pattern_def['severity'],
                    'security',
                    f"{pattern_def['label']}: potential sensitive content detected.",
                    pattern_def['fix'],
                    line,
                ))

    return findings
