"""
MCP Documentation Server

Exposes three tools that any MCP-compatible AI client can call:
  - search_docs   — keyword search across the indexed site
  - get_page      — fetch full text of a specific URL
  - list_pages    — list every indexed page with title + URL

Configuration (environment variables):
  DOCS_BASE_URL     URL to crawl, e.g. https://helpcenter.gamewarden.io/index-dod/
  DOCS_SITE_NAME    Display name shown to the AI client
  DOCS_MAX_PAGES    Max pages to crawl (default: 300)
  DOCS_CACHE_FILE   Path to cache file (default: .docs_cache.json in this directory)
  DOCS_NO_CACHE     Set to "1" to disable disk caching

  --- For sites behind a login wall (use one of the following) ---
  DOCS_COOKIE       Raw Cookie header value copied from your browser DevTools
  DOCS_AUTH_TOKEN   Bearer token (OAuth access token or API key)
  DOCS_BASIC_AUTH   username:password for HTTP Basic Auth sites

Usage:
  export DOCS_BASE_URL="https://helpcenter.gamewarden.io/index-dod/"
  export DOCS_SITE_NAME="GameWarden Help Center"
  python server.py
"""

import os
import sys
from mcp.server.fastmcp import FastMCP
from crawler import DocsCrawler

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get('DOCS_BASE_URL', 'https://helpcenter.gamewarden.io/index-dod/')
SITE_NAME = os.environ.get('DOCS_SITE_NAME', 'Documentation')
MAX_PAGES = int(os.environ.get('DOCS_MAX_PAGES', '300'))

_here = os.path.dirname(os.path.abspath(__file__))
_default_cache = os.path.join(_here, '.docs_cache.json')
CACHE_FILE = None if os.environ.get('DOCS_NO_CACHE') == '1' else os.environ.get('DOCS_CACHE_FILE', _default_cache)

# Force re-crawl if --refresh flag is passed
_force_refresh = '--refresh' in sys.argv

# Auth credentials — use whichever matches your site (only one is needed)
COOKIE     = os.environ.get('DOCS_COOKIE')
AUTH_TOKEN = os.environ.get('DOCS_AUTH_TOKEN')
BASIC_AUTH = os.environ.get('DOCS_BASIC_AUTH')

# ---------------------------------------------------------------------------
# Crawler (shared across all tool calls)
# ---------------------------------------------------------------------------

crawler = DocsCrawler(
    base_url=BASE_URL,
    max_pages=MAX_PAGES,
    cache_path=CACHE_FILE,
    cookie=COOKIE,
    auth_token=AUTH_TOKEN,
    basic_auth=BASIC_AUTH,
)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(SITE_NAME)


@mcp.tool()
def search_docs(query: str, limit: int = 5) -> str:
    """
    Search the documentation for pages matching a query.

    Parameters
    ----------
    query : str
        One or more keywords to search for.
    limit : int
        Maximum number of results to return (default 5, max 20).
    """
    limit = min(limit, 20)
    results = crawler.search(query, limit)

    if not results:
        return (
            f'No results found for "{query}" in {SITE_NAME}.\n'
            'Try different keywords or use list_pages() to browse all pages.'
        )

    sections = []
    for r in results:
        sections.append(
            f"### {r['title']}\n"
            f"URL: {r['url']}\n\n"
            f"{r['excerpt']}"
        )
    header = f'# Search results for "{query}" — {SITE_NAME}\n\n'
    return header + '\n\n---\n\n'.join(sections)


@mcp.tool()
def get_page(url: str) -> str:
    """
    Fetch and return the full text content of a documentation page.

    Parameters
    ----------
    url : str
        Full URL of the page to retrieve, e.g.
        https://helpcenter.gamewarden.io/index-dod/getting-started/
    """
    if not url.startswith('http'):
        return 'Please provide a full URL starting with http:// or https://'
    return crawler.get_page_content(url)


@mcp.tool()
def list_pages() -> str:
    """
    List all indexed documentation pages with their titles and URLs.
    Use this to discover what topics are covered before searching.
    """
    pages = crawler.list_pages()

    if not pages:
        return f'No pages have been indexed yet for {SITE_NAME}.'

    lines = [f"- [{p['title']}]({p['url']})" for p in pages]
    header = f'# {SITE_NAME} — {len(pages)} pages indexed\n\n'
    return header + '\n'.join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print(f'Starting MCP server for: {SITE_NAME}')
    print(f'Base URL : {BASE_URL}')
    print(f'Cache    : {CACHE_FILE or "disabled"}')

    _auth_method = (
        'cookie' if COOKIE else
        'bearer token' if AUTH_TOKEN else
        'basic auth' if BASIC_AUTH else
        'none (public site)'
    )
    print(f'Auth     : {_auth_method}')

    # Verify we can actually reach protected content before crawling
    if COOKIE or AUTH_TOKEN or BASIC_AUTH:
        try:
            if not crawler.check_auth():
                print(
                    '\n⚠ Auth check failed — the site returned what looks like a login page.\n'
                    '  Your credentials may be expired or incorrect.\n'
                    '  For cookie auth: re-login in your browser and copy a fresh Cookie value.\n'
                )
                sys.exit(1)
            print('  Auth check passed.')
        except PermissionError as e:
            print(f'\n⚠ {e}\n')
            sys.exit(1)

    print('Indexing site (this may take a moment on first run)...')
    count = crawler.crawl(force=_force_refresh)
    print(f'Indexed {count} pages. Ready.\n')

    mcp.run()
