"""
Slack API wrapper.

Handles authentication, pagination, rate limiting, and user name resolution.
All Slack API calls are isolated here so the rest of the agent never touches
the SDK directly.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackClient:
    """
    Thin wrapper around the Slack WebClient.

    Parameters
    ----------
    token : str
        Slack bot token (xoxb-...). Obtain from your Slack App configuration.
        See README for how to create the app and get the token.
    """

    # Seconds to wait between API calls to stay within Slack rate limits.
    # Tier 3 methods allow ~50 req/min; 1.2 s gives comfortable headroom.
    _RATE_LIMIT_SLEEP = 1.2
    _MAX_RETRIES = 5

    def __init__(self, token: str):
        self._client = WebClient(token=token)
        self._user_cache: Dict[str, str] = {}  # user_id → display name

    def _call_with_retry(self, fn, **kwargs):
        """Call a Slack SDK method, retrying on ratelimited errors."""
        for attempt in range(self._MAX_RETRIES):
            try:
                return fn(**kwargs)
            except SlackApiError as e:
                if e.response.get('error') == 'ratelimited':
                    retry_after = int(e.response.headers.get('Retry-After', 30))
                    print(f'  Rate limited — waiting {retry_after}s before retry...')
                    time.sleep(retry_after)
                else:
                    raise
        raise RuntimeError('Exceeded max retries due to Slack rate limiting')

    # ------------------------------------------------------------------
    # Channels
    # ------------------------------------------------------------------

    def list_channels(self, include_private: bool = False) -> List[Dict]:
        """
        Return all channels the bot has access to.

        Each dict contains: id, name, is_private, num_members.
        Requires scopes: channels:read, groups:read (for private channels).
        """
        channels = []
        cursor = None
        types = 'public_channel,private_channel' if include_private else 'public_channel'

        while True:
            resp = self._call_with_retry(
                self._client.conversations_list,
                types=types,
                exclude_archived=True,
                limit=200,
                cursor=cursor,
            )
            for ch in resp['channels']:
                channels.append({
                    'id': ch['id'],
                    'name': ch['name'],
                    'is_private': ch.get('is_private', False),
                    'num_members': ch.get('num_members', 0),
                })
            cursor = resp.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(self._RATE_LIMIT_SLEEP)

        return channels

    def resolve_channel_id(self, name_or_id: str) -> Optional[str]:
        """
        Return the channel ID for a given name (e.g. 'general') or pass
        through an ID unchanged.
        """
        if name_or_id.startswith('C'):
            return name_or_id  # already an ID
        channels = self.list_channels(include_private=True)
        for ch in channels:
            if ch['name'] == name_or_id.lstrip('#'):
                return ch['id']
        return None

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def get_all_messages(self, channel_id: str, days: int = 30) -> List[Dict]:
        """
        Fetch every message from a channel (threaded and standalone) within
        the last `days` days, in chronological order.

        Returns a list of conversation dicts:
          {
            channel_id, channel_name,
            ts,
            root: {author, text, timestamp},
            replies: [{author, text, timestamp}, ...]  # empty for standalone messages
          }
        """
        oldest = (datetime.utcnow() - timedelta(days=days)).timestamp()
        messages = self._fetch_history(channel_id, oldest)
        channel_name = self._channel_name(channel_id)

        # Sort chronologically (API returns newest-first)
        messages.sort(key=lambda m: float(m['ts']))

        conversations = []
        for msg in messages:
            replies = []
            if int(msg.get('reply_count', 0)) > 0:
                raw_replies = self._fetch_replies(channel_id, msg['ts'])
                replies = [
                    {
                        'author': self._user_name(r.get('user', '')),
                        'text': r.get('text', ''),
                        'timestamp': self._format_ts(r['ts']),
                    }
                    for r in raw_replies
                    if r['ts'] != msg['ts']  # exclude root from replies list
                ]
                time.sleep(self._RATE_LIMIT_SLEEP)

            conversations.append({
                'channel_id': channel_id,
                'channel_name': channel_name,
                'ts': msg['ts'],
                'root': {
                    'author': self._user_name(msg.get('user', '')),
                    'text': msg.get('text', ''),
                    'timestamp': self._format_ts(msg['ts']),
                },
                'replies': replies,
            })

        return conversations

    def get_threads(self, channel_id: str, days: int = 30) -> List[Dict]:
        """
        Fetch all threads (messages with at least one reply) from a channel
        posted within the last `days` days.

        Returns a list of thread dicts:
          {
            channel_id, channel_name,
            ts, permalink,
            root: {author, text, timestamp},
            replies: [{author, text, timestamp}, ...]
          }

        Requires scope: channels:history (public) or groups:history (private).
        """
        oldest = (datetime.utcnow() - timedelta(days=days)).timestamp()
        messages = self._fetch_history(channel_id, oldest)

        # Only keep messages that started a thread (have replies)
        thread_roots = [m for m in messages if int(m.get('reply_count', 0)) > 0]

        threads = []
        channel_name = self._channel_name(channel_id)

        for root in thread_roots:
            replies = self._fetch_replies(channel_id, root['ts'])
            thread = {
                'channel_id': channel_id,
                'channel_name': channel_name,
                'ts': root['ts'],
                'root': {
                    'author': self._user_name(root.get('user', '')),
                    'text': root.get('text', ''),
                    'timestamp': self._format_ts(root['ts']),
                },
                'replies': [
                    {
                        'author': self._user_name(r.get('user', '')),
                        'text': r.get('text', ''),
                        'timestamp': self._format_ts(r['ts']),
                    }
                    for r in replies
                    if r['ts'] != root['ts']  # exclude root from replies list
                ],
            }
            threads.append(thread)
            time.sleep(self._RATE_LIMIT_SLEEP)

        return threads

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_history(self, channel_id: str, oldest: float) -> List[Dict]:
        messages = []
        cursor = None
        while True:
            try:
                resp = self._call_with_retry(
                    self._client.conversations_history,
                    channel=channel_id,
                    oldest=str(oldest),
                    limit=200,
                    cursor=cursor,
                )
            except SlackApiError as e:
                print(f'  ⚠ Could not fetch history for {channel_id}: {e.response["error"]}')
                break
            messages.extend(resp.get('messages', []))
            cursor = resp.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(self._RATE_LIMIT_SLEEP)
        return messages

    def _fetch_replies(self, channel_id: str, thread_ts: str) -> List[Dict]:
        replies = []
        cursor = None
        while True:
            try:
                resp = self._call_with_retry(
                    self._client.conversations_replies,
                    channel=channel_id,
                    ts=thread_ts,
                    limit=200,
                    cursor=cursor,
                )
            except SlackApiError:
                break
            replies.extend(resp.get('messages', []))
            cursor = resp.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(self._RATE_LIMIT_SLEEP)
        return replies

    def _user_name(self, user_id: str) -> str:
        if not user_id:
            return 'Unknown'
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        try:
            resp = self._call_with_retry(self._client.users_info, user=user_id)
            profile = resp['user'].get('profile', {})
            name = (
                profile.get('display_name')
                or profile.get('real_name')
                or resp['user'].get('name')
                or user_id
            )
            self._user_cache[user_id] = name
            time.sleep(self._RATE_LIMIT_SLEEP)
            return name
        except SlackApiError:
            self._user_cache[user_id] = user_id
            return user_id

    def _channel_name(self, channel_id: str) -> str:
        try:
            resp = self._call_with_retry(self._client.conversations_info, channel=channel_id)
            return resp['channel'].get('name', channel_id)
        except SlackApiError:
            return channel_id

    @staticmethod
    def _format_ts(ts: str) -> str:
        try:
            return datetime.utcfromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M UTC')
        except Exception:
            return ts
