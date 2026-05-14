#!/usr/bin/env python3
"""
Temporary streaming / download link generator for leeched Telegram files.

Flow:
  1. Before upload  →  create_stream_token(name)   →  returns a 32-hex token
  2. After upload   →  set_stream_file_id(token, file_id, mime, msg_link)
  3. Web route      →  get_stream_data(token)       →  (file_id, name, mime)
  4. Web route streams / redirects to Telegram CDN
"""

from secrets import token_hex
from time import time
from logging import getLogger

LOGGER = getLogger(__name__)

_TOKEN_TTL: int = 86400  # 24 hours

# {token: {'file_id': str|None, 'name': str, 'mime': str, 'expires': float}}
_STREAM_STORE: dict = {}

# {telegram_msg_link: token}  ← populated after upload so tasks_listener can look up
_LINK_TOKEN: dict = {}


def create_stream_token(name: str) -> str:
    """
    Pre-create a token before the file is uploaded.
    The actual Telegram file_id is filled in later via set_stream_file_id().
    """
    tok = token_hex(16)
    _STREAM_STORE[tok] = {
        'file_id': None,
        'name': name,
        'mime': 'application/octet-stream',
        'expires': time() + _TOKEN_TTL,
    }
    return tok


def set_stream_file_id(token: str, file_id: str,
                       mime: str = '', msg_link: str = '') -> None:
    """
    Call immediately after the file is uploaded.
    Stores the Telegram file_id (and optionally the message link).
    """
    entry = _STREAM_STORE.get(token)
    if not entry:
        return
    entry['file_id'] = file_id
    if mime:
        entry['mime'] = mime
    if msg_link:
        _LINK_TOKEN[msg_link] = token


def get_stream_data(token: str):
    """
    Return (file_id, name, mime) or None if expired / file_id not yet set.
    """
    entry = _STREAM_STORE.get(token)
    if not entry:
        return None
    if time() > entry['expires']:
        _STREAM_STORE.pop(token, None)
        return None
    if not entry['file_id']:
        return None
    return entry['file_id'], entry['name'], entry['mime']


def get_token_for_link(msg_link: str):
    """Return the stream token for a Telegram message link, or None."""
    return _LINK_TOKEN.get(msg_link)


def build_stream_url(token: str, base_url: str) -> str:
    return f"{base_url.rstrip('/')}/stream/{token}"


def purge_expired() -> None:
    """Clean up expired tokens (call from a scheduler or periodic task)."""
    now = time()
    dead = [t for t, v in list(_STREAM_STORE.items()) if v['expires'] < now]
    for t in dead:
        _STREAM_STORE.pop(t, None)
    live = set(_STREAM_STORE)
    for lnk in [l for l, t in list(_LINK_TOKEN.items()) if t not in live]:
        _LINK_TOKEN.pop(lnk, None)
