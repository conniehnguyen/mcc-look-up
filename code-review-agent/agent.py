"""
Code Review Agent
=================
This is the core of the agent — the loop that drives the model
to use tools until it has enough information to write a review.

How it works:
  1. We send the model a task + a list of tools it can use
  2. The model replies with a tool call (e.g. list_files)
  3. We run the tool and send the result back to the model
  4. Repeat until the model stops calling tools and writes the review

Run:
  python3 agent.py <path-to-codebase>
  python3 agent.py .                    ← review current directory
"""

import json
import os
import sys
import ollama
from prompts import SYSTEM_PROMPT
from tools import TOOL_SCHEMAS, run_tool
import tools

MODEL = "qwen2.5-coder:7b"
MAX_ITERATIONS = 20  # safety limit so the agent doesn't loop forever


def print_step(label: str, content: str = ""):
    """Print a clearly visible step so you can follow along."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)
    if content:
        print(content)


SOURCE_EXTENSIONS = {".html", ".js", ".ts", ".jsx", ".tsx", ".py", ".css"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}


def collect_source_files(path: str) -> list[str]:
    """Walk the directory and return paths of all source files."""
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if any(f.endswith(ext) for ext in SOURCE_EXTENSIONS):
                found.append(os.path.join(root, f))
    return sorted(found)


def run_agent(target_path: str):
    print_step(f"Starting code review agent", f"Target: {target_path}\nModel:  {MODEL}")

    # Pre-load source files so the model has real content to analyze.
    # Smaller models like llama3.1 struggle to use file-navigation tools reliably,
    # so we give them the code upfront and let them focus purely on analysis.
    source_files = collect_source_files(target_path)
    print(f"\nFound {len(source_files)} source file(s):")
    for f in source_files:
        print(f"  {f}")

    file_contents = []
    for fpath in source_files:
        content = tools.read_file(fpath)
        file_contents.append(f"### File: {fpath}\n```\n{content}\n```")

    all_code = "\n\n".join(file_contents)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Review this codebase for bugs and security issues. "
                f"Go through the checklist in your instructions line by line.\n\n"
                f"Here are all the source files:\n\n{all_code}\n\n"
                "Write your structured report with specific findings and line numbers."
            ),
        }
    ]

    iteration = 0

    # ── Agent loop ────────────────────────────────────────────────────────────
    while iteration < MAX_ITERATIONS:
        iteration += 1
        print_step(f"Iteration {iteration} — asking model what to do next")

        # Send the full conversation + available tools to the model
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )

        message = response.message

        # Add the model's response to the conversation history
        messages.append({"role": "assistant", "content": message.content, "tool_calls": message.tool_calls})

        # ── Did the model call a tool? ─────────────────────────────────────
        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments

                print(f"\n→ Model called tool: {tool_name}")
                print(f"  Arguments: {json.dumps(tool_args, indent=2)}")

                # Run the actual tool (read a file, search code, etc.)
                result = run_tool(tool_name, tool_args)

                # Show a preview so you can follow along
                preview = result[:300] + "..." if len(result) > 300 else result
                print(f"\n  Result preview:\n{preview}")

                # Feed the tool result back into the conversation
                messages.append({
                    "role": "tool",
                    "content": result,
                })

        else:
            # ── No tool call = model is done, this is the final review ────
            print_step("Review complete — final report")
            print(message.content)
            return message.content

    print_step("Max iterations reached", "The agent hit the iteration limit. Partial results above.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    run_agent(path)
