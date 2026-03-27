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
Your job is to decide whether the thread contains a clear question and a
useful answer that would help future readers, and if so, extract a FAQ entry.

Return EXACTLY one of:

  FAQ_ENTRY
  QUESTION: <one concise sentence — the question being asked>
  ANSWER: <clear, complete answer in plain English — 1 to 5 sentences>
  TAGS: <comma-separated lowercase keywords, e.g. authentication, setup, docker>

  or

  NO_FAQ

Rules:
- Return NO_FAQ if the thread is casual chat, a standup update, an emoji
  reaction, a complaint with no resolution, or unclear.
- Return NO_FAQ if the thread has no meaningful answer (e.g. "not sure",
  "ask X person").
- Rewrite the question and answer in clean, professional language — do not
  copy Slack slang, @mentions, or emoji.
- The answer should be self-contained: a reader should not need to read the
  original thread to understand it.
- If the thread contains multiple questions, extract only the primary one.
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
    Analyse a single Slack thread and return a FAQ entry dict, or None if
    the thread is not FAQ-worthy.

    Return dict shape:
      {
        question: str,
        answer: str,
        tags: [str],
        source_channel: str,
        source_date: str,
      }
    """
    try:
        import google.generativeai as genai

        api_key = os.environ.get('GOOGLE_API_KEY')
        if not api_key:
            print('  ⚠ GOOGLE_API_KEY not set — skipping AI analysis.')
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            system_instruction=SYSTEM_PROMPT,
        )

        thread_text = _format_thread(thread)
        response = model.generate_content(
            f'Analyse this Slack thread and return a FAQ entry or NO_FAQ:\n\n{thread_text}'
        )
        text = (response.text or '').strip()

        if 'NO_FAQ' in text:
            return None

        return _parse_response(text, thread)

    except Exception as e:
        print(f'  ⚠ AI analysis failed: {e}')
        return None


def _parse_response(text: str, thread: Dict) -> Optional[Dict]:
    """Extract structured fields from the LLM response."""
    question_m = re.search(r'QUESTION:\s*(.+)', text)
    answer_m = re.search(r'ANSWER:\s*(.+?)(?=\nTAGS:|\Z)', text, re.DOTALL)
    tags_m = re.search(r'TAGS:\s*(.+)', text)

    if not question_m or not answer_m:
        return None

    tags_raw = tags_m.group(1).strip() if tags_m else ''
    tags = [t.strip().lower() for t in tags_raw.split(',') if t.strip()]

    return {
        'question': question_m.group(1).strip(),
        'answer': answer_m.group(1).strip(),
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
        words = set(faq['question'].lower().split())
        is_duplicate = False
        for existing in unique:
            existing_words = set(existing['question'].lower().split())
            overlap = len(words & existing_words) / max(len(words | existing_words), 1)
            if overlap > 0.7:  # 70% word overlap → treat as duplicate
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(faq)
    return unique
