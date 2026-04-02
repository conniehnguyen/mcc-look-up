"""
FAQ generator.

Takes a Slack thread (root message + replies) and asks an LLM to decide
whether it contains a useful Q&A worth turning into a FAQ entry.

Uses Gemini via the GOOGLE_API_KEY environment variable, consistent with
the docs-review-agent. Swap the AI backend by replacing run_ai_analysis().
"""

import os
import re
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a technical documentation writer. You will be given a Slack thread.
Your job is to decide whether the thread is worth summarising for future readers.

A thread is worth summarising if it contains:
- A meaningful question (even without a full answer), OR
- A meaningful question with an informative discussion or resolution.

Return EXACTLY one of:

  SUMMARY
  TITLE: <one short sentence capturing the core topic>
  QUESTION: <the question being asked, rewritten clearly>
  SUMMARY: <2 to 4 sentences summarising the discussion and any conclusions or next steps>
  RESOLVED: yes | no | partial
  TAGS: <comma-separated lowercase keywords, e.g. authentication, setup, docker>

  or

  SKIP

Rules:
- Return SKIP only if the thread is purely casual chat, a standup update,
  an emoji-only reaction, or completely off-topic noise with no substance.
- A thread with a real question but no answer is still worth summarising —
  mark it RESOLVED: no.
- A thread with a partial answer or ongoing discussion is RESOLVED: partial.
- Rewrite everything in clean, professional language — strip Slack slang,
  @mentions, and emoji.
- The summary should be self-contained: a reader should understand the gist
  without reading the original thread.
"""


# ---------------------------------------------------------------------------
# Thread formatter
# ---------------------------------------------------------------------------

def _format_thread(thread: Dict) -> str:
    """Convert a thread dict into a plain-text block for the LLM."""
    lines = [
        f"Channel: #{thread['channel_name']}",
        f"Date: {thread['root']['timestamp']}",
        '',
        f"[{thread['root']['author']}]: {thread['root']['text']}",
    ]
    for reply in thread['replies']:
        lines.append(f"[{reply['author']}]: {reply['text']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# AI analysis
# ---------------------------------------------------------------------------

def generate_faq(thread: Dict) -> Optional[Dict]:
    """
    Analyse a single Slack thread and return a summary dict, or None if
    the thread is not worth summarising.

    Return dict shape:
      {
        title: str,
        question: str,
        summary: str,
        resolved: str,  # 'yes' | 'no' | 'partial'
        tags: [str],
        source_channel: str,
        source_date: str,
      }
    """
    try:
        from google import genai
        from google.genai import types

        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            print('  ⚠ GOOGLE_API_KEY not set — skipping AI analysis.')
            return None

        client = genai.Client(api_key=api_key)
        thread_text = _format_thread(thread)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=f'Analyse this Slack thread and return a summary or SKIP:\n\n{thread_text}',
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        text = (response.text or '').strip()

        if 'SKIP' in text:
            return None

        return _parse_response(text, thread)

    except Exception as e:
        print(f'  ⚠ AI analysis failed: {e}')
        return None


def _parse_response(text: str, thread: Dict) -> Optional[Dict]:
    """Extract structured fields from the LLM response."""
    title_m = re.search(r'TITLE:\s*(.+)', text)
    question_m = re.search(r'QUESTION:\s*(.+)', text)
    summary_m = re.search(r'SUMMARY:\s*(.+?)(?=\nRESOLVED:|\nTAGS:|\Z)', text, re.DOTALL)
    resolved_m = re.search(r'RESOLVED:\s*(\w+)', text)
    tags_m = re.search(r'TAGS:\s*(.+)', text)

    if not question_m or not summary_m:
        return None

    tags_raw = tags_m.group(1).strip() if tags_m else ''
    tags = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]

    return {
        'title': title_m.group(1).strip() if title_m else question_m.group(1).strip(),
        'question': question_m.group(1).strip(),
        'summary': summary_m.group(1).strip(),
        'resolved': (resolved_m.group(1).strip().lower() if resolved_m else 'unknown'),
        'tags': tags,
        'source_channel': thread['channel_name'],
        'source_date': thread['root']['timestamp'],
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(faqs: List[Dict]) -> List[Dict]:
    """
    Remove FAQ entries whose questions are near-identical.
    Simple word-overlap heuristic — no embedding model required.
    """
    unique = []
    for faq in faqs:
        words = set(faq['title'].lower().split())
        is_duplicate = False
        for existing in unique:
            existing_words = set(existing['title'].lower().split())
            overlap = len(words & existing_words) / max(len(words | existing_words), 1)
            if overlap > 0.7:  # 70% word overlap → treat as duplicate
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(faq)
    return unique
