from __future__ import annotations

import re
from typing import Optional

import requests


_CHANNEL_ID_RE = re.compile(r'"channelId"\s*:\s*"(UC[a-zA-Z0-9_-]{20,})"')
_BROWSE_ID_RE = re.compile(r'"browseId"\s*:\s*"(UC[a-zA-Z0-9_-]{20,})"')


def resolve_channel_id(youtube_channel_url: str, *, timeout_s: int = 15) -> Optional[str]:
    """
    Best-effort resolver: given a URL like https://www.youtube.com/@SomeHandle
    returns the canonical channel_id (UC...).

    This is intentionally heuristic and may break if YouTube changes markup.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; meme_finder/0.1; +https://github.com/)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # YouTube often embeds the canonical channel id as "browseId" on /about pages.
    candidates = [youtube_channel_url, youtube_channel_url.rstrip("/") + "/about"]
    for url in candidates:
        r = requests.get(url, headers=headers, timeout=timeout_s)
        if r.status_code != 200:
            continue

        m = _CHANNEL_ID_RE.search(r.text) or _BROWSE_ID_RE.search(r.text)
        if m:
            return m.group(1)

    return None


def youtube_rss_from_channel_id(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

