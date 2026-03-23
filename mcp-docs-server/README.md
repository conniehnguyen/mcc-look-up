# MCP Documentation Server

An MCP (Model Context Protocol) server that crawls a documentation site and exposes it as a set of tools that any MCP-compatible AI client can query — Claude, Cursor, Gemini, ChatGPT with plugins, and others.

## Tools exposed

| Tool | Description |
| --- | --- |
| `search_docs(query, limit?)` | Keyword search across all indexed pages |
| `get_page(url)` | Fetch full text of a specific page |
| `list_pages()` | List every indexed page with its title and URL |

## Requirements

- Python 3.10+
- `pip install -r requirements.txt`

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the doc site

Set these environment variables before starting the server:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `DOCS_BASE_URL` | Yes | GameWarden Help Center URL | Root URL of the doc site to crawl |
| `DOCS_SITE_NAME` | No | `Documentation` | Display name shown to the AI client |
| `DOCS_MAX_PAGES` | No | `300` | Maximum pages to crawl — see note below |
| `DOCS_CACHE_FILE` | No | `.docs_cache.json` | Path to the disk cache file |
| `DOCS_NO_CACHE` | No | — | Set to `1` to disable disk caching |

> **Not sure what to set for `DOCS_MAX_PAGES`?** Leave it unset. The default of `300` covers most documentation sites. The server will stop crawling once it reaches that limit and tell you how many pages were indexed in the startup output. If you see the number is exactly 300 and you suspect the site has more, increase the value (e.g. `500` or `1000`). If the site is small and you want faster startup on first run, a lower value like `50` is fine.
>
> To check how many pages your site has before committing to a number, look for a sitemap at `<your-site>/sitemap.xml` — most doc platforms generate one automatically.

```bash
export DOCS_BASE_URL="https://helpcenter.gamewarden.io/index-dod/"
export DOCS_SITE_NAME="GameWarden Help Center"
```

### 3. Start the server

```bash
python server.py
```

On first run the server crawls the site and builds an index (may take a minute depending on site size). Subsequent starts load from the cache and are instant.

To force a fresh crawl:

```bash
python server.py --refresh
```

## Connecting AI clients

MCP (Model Context Protocol) is an open standard. You do not need a desktop AI app — many users connect through a VS Code plugin or another editor extension. The setup pattern is the same regardless: you point the client at `server.py` and pass your env vars in a config file. The config file location is the only thing that differs between clients.

**Which path applies to you?**

| If you use… | Go to… |
| --- | --- |
| GitHub Copilot inside VS Code | [VS Code GitHub Copilot](#vs-code-github-copilot-agent-mode) |
| Continue.dev inside VS Code or JetBrains | [Continue.dev](#continuedev-vs-code--jetbrains) |
| Cursor editor | [Cursor](#cursor) |
| Windsurf editor | [Windsurf](#windsurf) |
| Claude desktop app | [Claude Desktop](#claude-desktop) |
| Claude in the terminal | [Claude Code CLI](#claude-code-cli) |
| ChatGPT or Gemini | [ChatGPT and Gemini](#chatgpt-and-gemini) |

> **Before you start:** find the absolute path to `server.py` on your machine — you will paste it into whichever config below applies to you.
>
> ```bash
> # macOS / Linux
> cd mcp-docs-server && pwd
> # → e.g. /Users/yourname/Documents/mcp-docs-server
> # Full path to use: /Users/yourname/Documents/mcp-docs-server/server.py
> ```
>
> On Windows, use `cd mcp-docs-server && echo %cd%` in Command Prompt.

---

### VS Code GitHub Copilot agent mode

Requires VS Code 1.99+ with GitHub Copilot Chat enabled.

Create `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "gamewarden-docs": {
      "type": "stdio",
      "command": "python3",
      "args": ["/absolute/path/to/mcp-docs-server/server.py"],
      "env": {
        "DOCS_BASE_URL": "https://helpcenter.gamewarden.io/index-dod/",
        "DOCS_SITE_NAME": "GameWarden Help Center"
      }
    }
  }
}
```

Open the Copilot Chat panel, switch to **Agent mode**, and the docs tools will appear in the tool list.

---

### Cursor

**For a single project** — create `.cursor/mcp.json` in your project root.
**Globally** — create `~/.cursor/mcp.json`.

```json
{
  "mcpServers": {
    "gamewarden-docs": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp-docs-server/server.py"],
      "env": {
        "DOCS_BASE_URL": "https://helpcenter.gamewarden.io/index-dod/",
        "DOCS_SITE_NAME": "GameWarden Help Center"
      }
    }
  }
}
```

Restart Cursor. In Agent mode (Ctrl+I / Cmd+I), the docs tools will be available automatically. You can ask:

> "Using the GameWarden docs, how do I configure SSO?"

---

### Claude Desktop

**Config file location:**

| OS | Path |
| --- | --- |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Open the file (create it if it does not exist) and add the `mcpServers` block:

```json
{
  "mcpServers": {
    "gamewarden-docs": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp-docs-server/server.py"],
      "env": {
        "DOCS_BASE_URL": "https://helpcenter.gamewarden.io/index-dod/",
        "DOCS_SITE_NAME": "GameWarden Help Center"
      }
    }
  }
}
```

Restart Claude Desktop after saving. A hammer icon will appear in the chat input bar when the server is connected. You can then ask Claude things like:

> "Search the GameWarden docs for container registry setup."

---

### Windsurf

Create `~/.codeium/windsurf/mcp_config.json` (or open **Windsurf Settings → MCP**):

```json
{
  "mcpServers": {
    "gamewarden-docs": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp-docs-server/server.py"],
      "env": {
        "DOCS_BASE_URL": "https://helpcenter.gamewarden.io/index-dod/",
        "DOCS_SITE_NAME": "GameWarden Help Center"
      }
    }
  }
}
```

Restart Windsurf. The tools are available in Cascade (agent mode).

---

### Continue.dev (VS Code / JetBrains)

Add to `~/.continue/config.json` under the `mcpServers` key:

```json
{
  "mcpServers": [
    {
      "name": "gamewarden-docs",
      "command": "python3",
      "args": ["/absolute/path/to/mcp-docs-server/server.py"],
      "env": {
        "DOCS_BASE_URL": "https://helpcenter.gamewarden.io/index-dod/",
        "DOCS_SITE_NAME": "GameWarden Help Center"
      }
    }
  ]
}
```

---

### Claude Code (CLI)

```bash
claude mcp add gamewarden-docs \
  --env DOCS_BASE_URL=https://helpcenter.gamewarden.io/index-dod/ \
  --env DOCS_SITE_NAME="GameWarden Help Center" \
  -- python3 /absolute/path/to/mcp-docs-server/server.py
```

To verify the server is registered:

```bash
claude mcp list
```

---

### ChatGPT and Gemini

ChatGPT and Gemini do not currently support MCP directly. Alternatives:

- **ChatGPT**: Use the [Custom GPT](https://openai.com/blog/introducing-gpts) feature with an OpenAPI-compatible wrapper, or wait for OpenAI's native MCP support (announced but not yet generally available as of mid-2025).
- **Gemini**: Use Gemini in tools that support MCP (such as Cursor or Continue.dev) with a Gemini model selected — the MCP server works at the tool layer, independent of the underlying model.

---

### Verifying the connection

Regardless of which client you use, you can confirm the server is working by asking your AI tool:

> "List all pages in the GameWarden documentation."

If the server is connected, it will call `list_pages()` and return the full index. If not, check that the path to `server.py` is correct and that Python 3.10+ is on your system PATH.

## Reusing for a different doc site

Only the environment variables change — no code edits needed:

```bash
export DOCS_BASE_URL="https://docs.myotherproduct.com/"
export DOCS_SITE_NAME="My Other Product Docs"
export DOCS_CACHE_FILE=".my_other_product_cache.json"
python server.py
```

## How it works

1. On startup, `crawler.py` fetches the base URL and follows all links that stay within the same domain prefix.
2. Each page is stripped of navigation, headers, footers, and scripts — only the main content text is kept.
3. The index is written to a local JSON cache file so subsequent starts are instant.
4. `search_docs` scores pages by counting query term occurrences (title matches count 3×) and returns excerpts around the best match.
5. `get_page` fetches any URL live and returns clean text.

## Limitations

- Search is keyword-based, not semantic. For semantic search, the index could be extended with an embedding model.
- Pages that require authentication or JavaScript rendering will not be crawled.
- Tab-based anchors (e.g. `#__tabbed_1_2`) resolve to the parent page — anchor-level navigation is not validated.
