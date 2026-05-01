from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

import feedparser
from dateutil import parser as date_parser

from .types import Item, Source


def _parse_published(entry: dict) -> Optional[datetime]:
    for key in ("published", "updated", "pubDate"):
        val = entry.get(key)
        if not val:
            continue
        try:
            dt = date_parser.parse(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def fetch_items_for_source(source: Source, since: datetime) -> List[Item]:
    parsed = feedparser.parse(source.feed_url)
    items: List[Item] = []
    for e in parsed.entries or []:
        url = e.get("link") or e.get("id") or ""
        title = (e.get("title") or "").strip()
        published_at = _parse_published(e)
        summary = (e.get("summary") or e.get("description") or None)

        item = Item(
            source_name=source.name,
            platform=source.platform,
            title=title or "(untitled)",
            url=url,
            published_at=published_at,
            summary=summary.strip() if isinstance(summary, str) else None,
        )

        # If feed doesn't provide times, keep it (we'll rely on daily run).
        if published_at is None or published_at >= since:
            items.append(item)

    # Prefer newest first.
    items.sort(key=lambda i: i.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return items


def fetch_all(sources: Iterable[Source], lookback_hours: int = 24) -> List[Item]:
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    out: List[Item] = []
    for s in sources:
        out.extend(fetch_items_for_source(s, since=since))
    return out

