"""
Slack FAQ Agent
===============
Scouts Slack channels for Q&A threads and generates FAQ markdown files
ready to add to your documentation site.

Configuration (environment variables):
  SLACK_BOT_TOKEN   Your Slack bot token — required.
                    Format: xoxb-...
                    See README for how to create the Slack app and get the token.

  GOOGLE_API_KEY    Gemini API key for AI-powered FAQ extraction.
                    Without this, the agent skips AI analysis and exports nothing.

Usage:
  python agent.py --channels general,help,support
  python agent.py --channels general --days 14 --output faqs/output.md
  python agent.py --list-channels
"""

import argparse
import os
import sys

from slack_client import SlackClient
from faq_generator import generate_faq, deduplicate
from exporter import export_markdown, export_raw_markdown

# ---------------------------------------------------------------------------
# Configuration — set these as environment variables, never hardcode values
# ---------------------------------------------------------------------------

# !! PLACEHOLDER — set this before running !!
# export SLACK_BOT_TOKEN="xoxb-your-token-here"
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')

# !! PLACEHOLDER — set this before running !!
# export GOOGLE_API_KEY="your-gemini-api-key-here"
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

DEFAULT_DAYS = 30
DEFAULT_OUTPUT = 'output/faqs.md'


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_raw(
    channels: list[str],
    days: int,
    output_path: str,
    include_private: bool,
) -> None:
    """Export all conversations to markdown without AI processing."""
    if not SLACK_BOT_TOKEN:
        print('\n⚠ SLACK_BOT_TOKEN is not set.\n'
              '  export SLACK_BOT_TOKEN="xoxb-your-token-here"\n')
        sys.exit(1)

    client = SlackClient(SLACK_BOT_TOKEN)

    print(f'\nResolving {len(channels)} channel(s)...')
    channel_ids = []
    for name in channels:
        cid = client.resolve_channel_id(name.lstrip('#'))
        if cid:
            channel_ids.append((name.lstrip('#'), cid))
            print(f'  ✓ #{name.lstrip("#")} → {cid}')
        else:
            print(f'  ✗ #{name.lstrip("#")} not found — check the name and that the bot is invited')

    if not channel_ids:
        print('\nNo valid channels found. Exiting.')
        sys.exit(1)

    all_conversations = []
    for ch_name, ch_id in channel_ids:
        print(f'\nFetching all messages from #{ch_name} (last {days} days)...')
        convos = client.get_all_messages(ch_id, days=days)
        print(f'  Found {len(convos)} message(s)')
        all_conversations.extend(convos)

    if not all_conversations:
        print('\nNo messages found in the specified channels and time range.')
        sys.exit(0)

    print(f'\nExporting to {output_path}...')
    export_raw_markdown(all_conversations, output_path)
    print('\nDone. Open the file and paste into Claude or Gemini for summarisation.')


def run(
    channels: list[str],
    days: int,
    output_path: str,
    include_private: bool,
) -> None:
    if not SLACK_BOT_TOKEN:
        print(
            '\n⚠ SLACK_BOT_TOKEN is not set.\n'
            '  Set it before running:\n'
            '    export SLACK_BOT_TOKEN="xoxb-your-token-here"\n'
            '  See README for how to create a Slack app and get the token.\n'
        )
        sys.exit(1)

    if not GOOGLE_API_KEY:
        print(
            '\n⚠ GOOGLE_API_KEY is not set.\n'
            '  Set it before running:\n'
            '    export GOOGLE_API_KEY="your-gemini-api-key-here"\n'
        )
        sys.exit(1)

    client = SlackClient(SLACK_BOT_TOKEN)

    # Resolve channel names to IDs
    print(f'\nResolving {len(channels)} channel(s)...')
    channel_ids = []
    for name in channels:
        cid = client.resolve_channel_id(name.lstrip('#'))
        if cid:
            channel_ids.append((name.lstrip('#'), cid))
            print(f'  ✓ #{name.lstrip("#")} → {cid}')
        else:
            print(f'  ✗ #{name.lstrip("#")} not found — check the name and that the bot is invited')

    if not channel_ids:
        print('\nNo valid channels found. Exiting.')
        sys.exit(1)

    # Fetch threads from all channels
    all_threads = []
    for ch_name, ch_id in channel_ids:
        print(f'\nFetching threads from #{ch_name} (last {days} days)...')
        threads = client.get_threads(ch_id, days=days)
        print(f'  Found {len(threads)} thread(s) with replies')
        all_threads.extend(threads)

    if not all_threads:
        print('\nNo threads found in the specified channels and time range.')
        sys.exit(0)

    # Run AI analysis on each thread
    print(f'\nAnalysing {len(all_threads)} thread(s) with Gemini...')
    faqs = []
    for i, thread in enumerate(all_threads, 1):
        print(f'  [{i}/{len(all_threads)}] #{thread["channel_name"]} — {thread["root"]["timestamp"]}')
        entry = generate_faq(thread)
        if entry:
            faqs.append(entry)
            print(f'    → FAQ: {entry["question"][:80]}')
        else:
            print('    → Skipped (not FAQ-worthy)')

    print(f'\n{len(faqs)} FAQ entries extracted from {len(all_threads)} threads.')

    if not faqs:
        print('Nothing to export.')
        sys.exit(0)

    # Deduplicate
    before = len(faqs)
    faqs = deduplicate(faqs)
    removed = before - len(faqs)
    if removed:
        print(f'Removed {removed} near-duplicate entrie(s).')

    # Export to markdown
    print(f'\nExporting to {output_path}...')
    export_markdown(faqs, output_path)
    print('\nDone. Review the output before adding it to your doc site.')


# ---------------------------------------------------------------------------
# Channel listing utility
# ---------------------------------------------------------------------------

def list_channels(include_private: bool) -> None:
    if not SLACK_BOT_TOKEN:
        print('⚠ SLACK_BOT_TOKEN is not set.')
        sys.exit(1)
    client = SlackClient(SLACK_BOT_TOKEN)
    channels = client.list_channels(include_private=include_private)
    print(f'\n{"#":<30} {"ID":<15} {"Members":>8}  {"Private"}')
    print('-' * 65)
    for ch in sorted(channels, key=lambda c: c['name']):
        priv = '🔒' if ch['is_private'] else ''
        print(f'#{ch["name"]:<29} {ch["id"]:<15} {ch["num_members"]:>8}  {priv}')
    print(f'\n{len(channels)} channel(s) visible to this bot.')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate FAQ markdown from Slack threads.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        '--channels', '-c',
        help='Comma-separated list of channel names or IDs, e.g. general,help,support',
    )
    parser.add_argument(
        '--days', '-d',
        type=int,
        default=DEFAULT_DAYS,
        help=f'How many days back to look for threads (default: {DEFAULT_DAYS})',
    )
    parser.add_argument(
        '--output', '-o',
        default=DEFAULT_OUTPUT,
        help=f'Output markdown file path (default: {DEFAULT_OUTPUT})',
    )
    parser.add_argument(
        '--include-private',
        action='store_true',
        help='Include private channels (bot must be a member)',
    )
    parser.add_argument(
        '--list-channels',
        action='store_true',
        help='Print all channels the bot can see and exit',
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help='Export all conversations as readable markdown without AI processing',
    )

    args = parser.parse_args()

    if args.list_channels:
        list_channels(include_private=args.include_private)
        return

    if not args.channels:
        parser.error('--channels is required unless --list-channels is used')

    channels = [c.strip() for c in args.channels.split(',') if c.strip()]

    if args.raw:
        run_raw(
            channels=channels,
            days=args.days,
            output_path=args.output,
            include_private=args.include_private,
        )
    else:
        run(
            channels=channels,
            days=args.days,
            output_path=args.output,
            include_private=args.include_private,
        )


if __name__ == '__main__':
    main()
