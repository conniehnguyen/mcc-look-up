"""
Tools the agent can call.

Each tool has two parts:
  1. A Python function that actually does the work
  2. A JSON schema that describes the tool to the model
"""

import os
import re

# ── Python functions ──────────────────────────────────────────────────────────

def list_files(path: str = ".") -> str:
    """Return a tree of files under `path`, skipping common noise dirs."""
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
    lines = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in sorted(dirs) if d not in SKIP]
        depth = root.replace(path, "").count(os.sep)
        indent = "  " * depth
        lines.append(f"{indent}{os.path.basename(root)}/")
        for f in sorted(files):
            lines.append(f"{indent}  {f}")
    return "\n".join(lines) if lines else "No files found."


def read_file(path: str) -> str:
    """Return the contents of a file with line numbers."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        numbered = [f"{i+1:4}: {line}" for i, line in enumerate(lines)]
        return "".join(numbered)
    except FileNotFoundError:
        return f"Error: file not found — {path}"
    except Exception as e:
        return f"Error reading {path}: {e}"


def search_code(path: str, pattern: str) -> str:
    """Search for a regex pattern across all text files under `path`.
    Returns matching lines with file name and line number."""
    SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    BINARY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
                   ".exe", ".bin", ".woff", ".woff2", ".ttf", ".eot"}
    results = []
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fname in files:
            if any(fname.endswith(ext) for ext in BINARY_EXTS):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{fpath}:{i}: {line.rstrip()}")
            except Exception:
                continue

    if not results:
        return f"No matches found for '{pattern}' in {path}"
    return "\n".join(results[:100])  # cap at 100 matches


# ── Tool dispatcher ───────────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "list_files": list_files,
    "read_file": read_file,
    "search_code": search_code,
}

def run_tool(name: str, args: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return fn(**args)


# ── JSON schemas (what the model sees) ───────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in a directory tree. Use this first to understand the structure of a codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Defaults to current directory.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for a pattern across all files in a directory. Useful for finding specific functions, variables, or suspicious patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to search in.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for.",
                    },
                },
                "required": ["path", "pattern"],
            },
        },
    },
]
