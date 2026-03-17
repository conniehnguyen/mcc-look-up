# Documentation Review Agent

Reviews a documentation repository against the **Microsoft Writing Style Guide**. Finds style violations, typos, broken links, and code block issues — and suggests a fix for every finding.

---

## What it checks

| Check | How |
| --- | --- |
| Microsoft style guide (passive voice, "please", "click", heading case, etc.) | Pattern matching + AI |
| Typos and misspellings | `pyspellchecker` library |
| Broken HTTP and relative links | Live network check |
| Code blocks missing a language tag or left unclosed | Pattern matching |

---

## Installation

### Step 1 — Install Python

Make sure you have Python 3.10 or later. Check by running:

```bash
python3 --version
```

If Python is not installed, download it from [python.org](https://python.org).

### Step 2 — Download the agent files

Copy the `docs-review-agent/` folder to your machine. It contains:

```text
docs-review-agent/
├── agent.py          ← entry point — run this
├── checks.py         ← typos, links, code block, style pattern checks
├── style_rules.py    ← Microsoft style guide rules
├── exemptions.py     ← saves and loads your exemptions
├── prompts.py        ← AI instructions
└── requirements.txt
```

### Step 3 — Install dependencies

In your terminal, navigate to the `docs-review-agent/` folder and run:

```bash
pip3 install -r requirements.txt
```

### Step 4 — Set up an AI model

The agent uses an AI model for deeper style analysis (passive voice, unclear instructions, tone). You have three options:

#### Option A: Ollama — free, runs on your machine (default)

1. Download Ollama from [ollama.com](https://ollama.com)
2. Open the Ollama app so it runs in the background
3. Pull a model:

```bash
ollama pull qwen2.5-coder:7b
```

No API key needed. The `agent.py` file is already configured to use this model.

#### Option B: Claude (Anthropic API)

1. Get an API key at [console.anthropic.com](https://console.anthropic.com) — new accounts get $5 free credit
2. Install the SDK: `pip3 install anthropic`
3. Open `agent.py` and replace the `run_ai_analysis` function's model call with:

```python
import anthropic

def run_ai_analysis(file_path: str, content: str) -> list[dict]:
    client = anthropic.Anthropic(api_key="your-api-key-here")  # or set ANTHROPIC_API_KEY env var
    findings = []
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Review this documentation file: {file_path}\n\n```\n{content[:6000]}\n```"
            }]
        )
        text = response.content[0].text
        # ... rest of the parsing logic stays the same
```

#### Option C: Gemini (Google AI)

1. Get an API key at [aistudio.google.com](https://aistudio.google.com) — free tier available
2. Install the SDK: `pip3 install google-generativeai`
3. Open `agent.py` and replace the model call in `run_ai_analysis` with:

```python
import google.generativeai as genai

def run_ai_analysis(file_path: str, content: str) -> list[dict]:
    genai.configure(api_key="your-api-key-here")  # or set GOOGLE_API_KEY env var
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=SYSTEM_PROMPT
    )
    findings = []
    try:
        response = model.generate_content(
            f"Review this documentation file: {file_path}\n\n```\n{content[:6000]}\n```"
        )
        text = response.text
        # ... rest of the parsing logic stays the same
```

> **Tip:** Store API keys as environment variables instead of pasting them into the code.
> Run `export ANTHROPIC_API_KEY="your-key"` (or `export GOOGLE_API_KEY="your-key"`) in your terminal,
> then read them in Python with `os.environ.get("ANTHROPIC_API_KEY")`.

---

## Pointing the agent at your documentation

The agent accepts any local path — a single file or an entire folder. It automatically finds all `.md`, `.mdx`, `.rst`, and `.txt` files inside that folder.

**Your docs stay on your machine.** The agent reads them directly from your file system. Nothing is uploaded anywhere (unless you use a cloud AI model, in which case the file content is sent to that API to generate the review).

```bash
# Review an entire docs folder
python3 agent.py /Users/yourname/projects/my-app/docs

# Review a single file
python3 agent.py /Users/yourname/projects/my-app/docs/getting-started.md

# Review the current directory
python3 agent.py .
```

---

## Running the agent

### Full review (style + typos + links + AI)

```bash
python3 agent.py /path/to/your/docs
```

### Without AI (faster — pattern checks and typos only)

```bash
python3 agent.py /path/to/your/docs --no-ai
```

### Without link checking (faster — skips network calls)

```bash
python3 agent.py /path/to/your/docs --no-links
```

### Both flags combined

```bash
python3 agent.py /path/to/your/docs --no-ai --no-links
```

---

## Exemptions

Some findings may not apply to your project — for example, a legacy document you plan to rewrite later, or a style rule that conflicts with your team's conventions.

At the end of every run, you are prompted to exempt findings by ID:

```text
Mark findings as exempt
Enter finding IDs (comma-separated), or press Enter to skip:
> a1b2c3d4, e5f6g7h8

Reason for exempting a1b2c3d4: Legacy content, updating in Q2
✓ Exempted a1b2c3d4
```

Exemptions are saved to `exemptions.json` in the agent folder. On future runs, exempt findings still appear in the report but are marked `[EXEMPT]` and not counted in the totals.

### Other exemption commands

```bash
# Show all saved exemptions
python3 agent.py --list-exemptions

# Remove an exemption (finding becomes active again)
python3 agent.py --remove-exempt a1b2c3d4
```

---

## Understanding the report

```text
🔴 [HIGH] STYLE  |  ID: a1b2c3d4
Rule: MS-006  |  Line 14
Found: See [here](https://example.com) for details.
Issue: Avoid generic link text. Screen readers read links out of context.
Fix:   Use descriptive link text that tells readers where they will go.

🟡 [MEDIUM] TYPO  |  ID: e5f6g7h8
Rule: TYPO  |  Line 22
Found: The recieve function returns a value.
Issue: Possible misspelling: "recieve" → did you mean "receive"?
Fix:   Replace "recieve" with "receive".
```

| Icon | Severity | Examples |
| --- | --- | --- |
| 🔴 | HIGH | Broken links, unclosed code fences, generic link text |
| 🟡 | MEDIUM | Passive voice, typos, "please", first-person "we" |
| 🔵 | LOW | "click" vs "select", exclamation points, Latin abbreviations |

---

## Customizing

**Add technical terms to the spell-check allowlist** — open `checks.py` and add words to the `ALLOWED_WORDS` set at the top of the file.

**Add or change style rules** — open `style_rules.py`. Each rule is a dictionary with these fields:

```python
{
    'code':     'MS-015',              # unique ID
    'name':     'avoid-contractions',  # slug
    'pattern':  r"\bdo not\b",         # regex to search for
    'severity': 'LOW',                 # HIGH / MEDIUM / LOW
    'message':  'Microsoft style encourages contractions.',
    'fix':      'Replace "do not" with "don\'t".',
    'scope':    'prose',               # prose = skip code blocks / all = check everywhere
}
```

**Change the AI model** — see the [Set up an AI model](#step-4--set-up-an-ai-model) section above.
