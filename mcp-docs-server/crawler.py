"""
DocsCrawler — site crawler and full-text index.

Reusable for any doc site: point it at a base URL and it will crawl all
pages under that URL, extract clean text, and support keyword search.

Results are cached to disk (index_cache.json) so the server doesn't
re-crawl on every startup. Call crawler.crawl(force=True) to refresh.

Authentication (for sites behind a login wall):
  Pass credentials via constructor or set env vars in server.py.
  Three methods are supported — use whichever matches your site:

  1. Session cookie  — log in via browser, copy the Cookie header value
  2. Bearer token   — API token or OAuth access token
  3. HTTP Basic Auth — username:password (base64-encoded automatically)

  The crawler cannot complete interactive OAuth/OIDC/SAML flows or MFA.
  For those sites, the session cookie method is the only practical option.
"""

import base64
import json
import os
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# HTML parsers (stdlib only — no dependencies)
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Strip HTML tags and return clean text + page title."""

    _SKIP = {'script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript'}

    def __init__(self):
        super().__init__()
        self.title = ''
        self._in_title = False
        self._skip_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._in_title = True
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._skip_depth == 0:
            text = data.strip()
            if text:
                self._parts.append(text)

    def get_text(self) -> str:
        return ' '.join(self._parts)


class _LinkExtractor(HTMLParser):
    """Collect all href values from <a> tags."""

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href:
                self.links.append(urllib.parse.urljoin(self.base_url, href))


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------

class DocsCrawler:
    """
    Crawl a documentation site and build a searchable in-memory index.

    Parameters
    ----------
    base_url : str
        Root URL. Only pages whose URLs start with this prefix are indexed.
    max_pages : int
        Hard cap to avoid runaway crawls.
    cache_path : str | None
        Path to a JSON file used to persist the index between runs.
        Pass None to disable caching.
    """

    def __init__(
        self,
        base_url: str,
        max_pages: int = 300,
        cache_path: Optional[str] = None,
        cookie: Optional[str] = None,
        auth_token: Optional[str] = None,
        basic_auth: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip('/') + '/'
        self.max_pages = max_pages
        self.cache_path = cache_path
        self._index: List[Dict] = []
        self._crawled = False

        # Build auth headers once — used in every request
        self._auth_headers: Dict[str, str] = {}
        if cookie:
            self._auth_headers['Cookie'] = cookie
        elif auth_token:
            self._auth_headers['Authorization'] = f'Bearer {auth_token}'
        elif basic_auth:
            encoded = base64.b64encode(basic_auth.encode()).decode()
            self._auth_headers['Authorization'] = f'Basic {encoded}'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self, force: bool = False) -> int:
        """
        Crawl the site and build the index. Returns the number of pages indexed.
        Uses disk cache if available unless force=True.
        """
        if not force and self._load_cache():
            return len(self._index)

        visited: set = set()
        queue = [self.base_url]
        self._index = []

        while queue and len(visited) < self.max_pages:
            url = queue.pop(0).split('#')[0]  # strip fragment
            if not url or url in visited or not self._is_same_site(url):
                continue
            visited.add(url)

            html = self._fetch(url)
            if not html:
                continue

            extractor = _TextExtractor()
            extractor.feed(html)
            title = extractor.title.strip() or url
            text = extractor.get_text()

            self._index.append({'url': url, 'title': title, 'text': text})

            link_ex = _LinkExtractor(url)
            link_ex.feed(html)
            for link in link_ex.links:
                clean = link.split('#')[0]
                if clean and clean not in visited and self._is_same_site(clean):
                    queue.append(clean)

        self._crawled = True
        self._save_cache()
        return len(self._index)

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Keyword search across indexed pages.
        Returns a list of {url, title, excerpt, score} dicts, best match first.
        """
        self._ensure_crawled()
        terms = query.lower().split()
        results = []

        for page in self._index:
            text_lower = page['text'].lower()
            title_lower = page['title'].lower()
            # Title matches are worth 3× more than body matches
            score = sum(
                text_lower.count(t) + title_lower.count(t) * 3
                for t in terms
            )
            if score == 0:
                continue
            # Build a short excerpt centred around the first query term
            idx = text_lower.find(terms[0]) if terms else 0
            start = max(0, idx - 120)
            excerpt = page['text'][start:start + 350].strip()
            results.append({
                'url': page['url'],
                'title': page['title'],
                'excerpt': excerpt,
                'score': score,
            })

        results.sort(key=lambda r: r['score'], reverse=True)
        return results[:limit]

    def get_page_content(self, url: str) -> str:
        """Fetch and return the full clean text of a single page."""
        html = self._fetch(url)
        if not html:
            return f'Could not fetch page: {url}'
        extractor = _TextExtractor()
        extractor.feed(html)
        title = extractor.title.strip() or url
        text = extractor.get_text()
        return f'# {title}\nURL: {url}\n\n{text}'

    def list_pages(self) -> List[Dict]:
        """Return all indexed pages as {url, title} dicts."""
        self._ensure_crawled()
        return [{'url': p['url'], 'title': p['title']} for p in self._index]

    def page_count(self) -> int:
        self._ensure_crawled()
        return len(self._index)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_crawled(self):
        if not self._crawled:
            self.crawl()

    def _is_same_site(self, url: str) -> bool:
        return url.startswith(self.base_url)

    def _fetch(self, url: str) -> str:
        try:
            headers = {'User-Agent': 'docs-mcp-server/1.0 (documentation indexer)'}
            headers.update(self._auth_headers)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                content_type = resp.headers.get('Content-Type', '')
                if 'html' not in content_type:
                    return ''
                return resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError(
                    f'Auth required for {url} (HTTP {e.code}). '
                    'Set DOCS_COOKIE, DOCS_AUTH_TOKEN, or DOCS_BASIC_AUTH.'
                )
            return ''
        except Exception:
            return ''

    def check_auth(self) -> bool:
        """
        Fetch the base URL and return True if the response looks like real
        content (not a login page). Call this before crawling to catch
        auth failures early with a clear error message.
        """
        try:
            html = self._fetch(self.base_url)
        except PermissionError as e:
            raise
        if not html:
            return False
        # Heuristic: login pages typically contain these patterns
        login_signals = ['login', 'sign in', 'sign-in', 'authenticate', 'password']
        text_lower = html.lower()
        # If the page has almost no content or is dominated by login signals,
        # it's likely an auth wall
        content_length = len(text_lower.strip())
        signal_hits = sum(text_lower.count(s) for s in login_signals)
        if content_length < 2000 and signal_hits >= 2:
            return False
        return True

    def _cache_key(self) -> str:
        """Derive a filename-safe key from the base URL."""
        safe = re.sub(r'[^\w]', '_', self.base_url)
        return safe[:80]

    def _load_cache(self) -> bool:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('base_url') != self.base_url:
                return False  # cache is for a different site
            self._index = data['pages']
            self._crawled = True
            return True
        except Exception:
            return False

    def _save_cache(self):
        if not self.cache_path:
            return
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {'base_url': self.base_url, 'pages': self._index},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass
