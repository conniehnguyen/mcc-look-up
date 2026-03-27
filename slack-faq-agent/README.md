# Slack FAQ Agent

Scouts Slack channels for Q&A threads and generates FAQ markdown files ready to add to your documentation site.

## How it works

1. Connects to your Slack workspace using a bot token
2. Fetches threads (messages with replies) from the channels you specify
3. Sends each thread to Gemini and asks: *"Is this a useful Q&A? If so, extract a FAQ entry."*
4. Deduplicates similar questions
5. Writes a markdown file grouped by channel, ready to review and publish

## Requirements

- Python 3.10+
- A Slack workspace where you can create or install an app
- A Gemini API key

## Setup

### Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Create a Slack app and get a bot token

You need a bot token (`xoxb-...`) to read channel messages. This requires either creating a Slack app yourself or asking your workspace admin to install one.

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App → From scratch**
2. Give it a name (e.g. `FAQ Bot`) and select your workspace
3. In the left sidebar go to **OAuth & Permissions**
4. Under **Bot Token Scopes** add the following scopes:

| Scope | What it allows |
| --- | --- |
| `channels:history` | Read messages from public channels |
| `channels:read` | List public channels |
| `groups:history` | Read messages from private channels (optional) |
| `groups:read` | List private channels (optional) |
| `users:read` | Resolve user IDs to display names |

5. Click **Install to Workspace** at the top of the page and approve
6. Copy the **Bot User OAuth Token** — it starts with `xoxb-`

> **Work machine note:** If your Slack workspace is managed by your company, creating an app may require admin approval. Submit a request through your IT helpdesk. The scopes above are all read-only.

### Step 3 — Invite the bot to channels

The bot can only read channels it has been invited to. In each channel you want to scan, type:

```
/invite @YourBotName
```

### Step 4 — Set environment variables

**Never paste your token into the code.** Set it as an environment variable:

```bash
export SLACK_BOT_TOKEN="xoxb-your-token-here"
export GOOGLE_API_KEY="your-gemini-api-key-here"
```

Or copy `.env.example` to `.env`, fill in your values, and load it:

```bash
cp .env.example .env
# edit .env with your values
source .env
```

> Add `.env` to your `.gitignore` so credentials are never committed.

### Step 5 — Run the agent

```bash
# See which channels the bot can access
python agent.py --list-channels

# Generate FAQs from specific channels (last 30 days)
python agent.py --channels general,help,support

# Specify a custom time range and output path
python agent.py --channels general,help --days 14 --output docs/faqs.md

# Include private channels (bot must be invited first)
python agent.py --channels my-private-channel --include-private
```

## Output

The agent writes a single markdown file grouped by channel:

```markdown
# Frequently Asked Questions

*Generated from Slack on 2026-03-26. Review before publishing.*

## Contents

- [general](#general) (3 entries)
- [support](#support) (7 entries)

---

## general

### How do I reset my API key?

Go to Settings → API Keys and click Regenerate. Your old key will be
invalidated immediately. Update any services using the old key before
regenerating.

**Tags:** `api` `authentication` `keys`

*Source: #general · 2026-03-10 14:32 UTC*
```

## Reviewing before publishing

The agent adds a note at the top of every file reminding you to review before publishing. Things to check:

- **Accuracy** — AI summaries can occasionally paraphrase incorrectly
- **Freshness** — answers that reference a specific release or workaround may go stale
- **Completeness** — some threads need context the AI couldn't infer
- **Privacy** — remove any entries that mention internal systems or personnel by name

## Scheduling (optional)

To run the agent automatically on a schedule, add a cron job:

```bash
# Run every Monday at 8 AM, scan the last 7 days, append to the same file
crontab -e

0 8 * * 1 cd /path/to/slack-faq-agent && \
  SLACK_BOT_TOKEN="xoxb-..." GOOGLE_API_KEY="..." \
  python agent.py --channels general,help,support --days 7 --output docs/faqs.md
```

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | CLI entry point and main pipeline |
| `slack_client.py` | Slack API wrapper — fetches channels, threads, user names |
| `faq_generator.py` | Gemini integration — decides if a thread is FAQ-worthy and extracts the entry |
| `exporter.py` | Writes FAQ entries to a formatted markdown file |
| `.env.example` | Template for your environment variables |
