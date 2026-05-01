from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Source:
    name: str
    platform: str
    feed_url: str
    homepage_url: Optional[str] = None


@dataclass(frozen=True)
class Item:
    source_name: str
    platform: str
    title: str
    url: str
    published_at: Optional[datetime]
    summary: Optional[str] = None

