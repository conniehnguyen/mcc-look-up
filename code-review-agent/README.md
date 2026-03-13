# Code Review Agent

A local AI agent that reads your codebase and identifies bugs and security issues. Runs entirely on your machine using Ollama — no API key or internet connection required.

---

## Requirements

- macOS (or Linux)
- Python 3.10 or later
- At least 8 GB of RAM

---

## 1. Installation

### Step 1 — Install Ollama

Download and install Ollama from [ollama.com](https://ollama.com), or with Homebrew:

```bash
brew install ollama
```

After installing, open the Ollama app so it runs in the background.

### Step 2 — Pull a model

```bash
ollama pull qwen2.5-coder:7b
```

This downloads a ~4.7 GB model optimized for code tasks. Only needed once.

### Step 3 — Install the Python dependency

```bash
pip3 install ollama
```

### Step 4 — Download the agent files

Copy the `code-review-agent/` folder to your machine. It contains:

```
code-review-agent/
├── agent.py      ← the agent loop (entry point)
├── tools.py      ← file reading and code search tools
└── prompts.py    ← system prompt that guides the model
```

---

## 2. Point the agent at your codebase

No configuration needed. You pass the path to your codebase when you run the agent (see next section).

The agent automatically finds all source files with these extensions:
`.html` `.js` `.ts` `.jsx` `.tsx` `.py` `.css`

It skips noise directories like `node_modules`, `.git`, `__pycache__`, `venv`, `build`, and `dist`.

---

## 3. Run the agent

Open a terminal, navigate to the `code-review-agent/` folder, then run:

```bash
python3 agent.py /path/to/your/project
```

**Examples:**

```bash
# Review a project in another folder
python3 agent.py ~/Documents/my-app

# Review the current directory
python3 agent.py .

# Review a single folder inside a project
python3 agent.py ~/Documents/my-app/src
```

The agent will print its progress as it works, then output a structured report with findings grouped by severity (CRITICAL / HIGH / MEDIUM / LOW).

---

## Changing the model

The agent uses `qwen2.5-coder:7b` by default. To switch models, open `agent.py` and change line 26:

```python
MODEL = "qwen2.5-coder:7b"   # change this to any model you have pulled
```

Other models to try:

```bash
ollama pull llama3.1          # general purpose, ~4.9 GB
ollama pull qwen2.5-coder:14b # better quality, requires ~9 GB RAM
```

---

## Troubleshooting

**"ollama not found"** — Make sure the Ollama app is open and running in your menu bar.

**The agent is slow** — This is normal for local models. A typical review takes 1–3 minutes depending on codebase size and your hardware.

**The model gives a generic report** — Smaller models (7B) sometimes describe code instead of finding specific issues. Try a larger model like `qwen2.5-coder:14b`, or reduce the amount of code being reviewed by pointing the agent at a specific subfolder.
