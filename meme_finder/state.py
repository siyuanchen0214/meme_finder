from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Tuple

from .types import Item


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_title(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def _is_similar_title(a: str, b: str, *, threshold: float = 0.92) -> bool:
    a_n = _norm_title(a)
    b_n = _norm_title(b)
    if not a_n or not b_n:
        return False
    if a_n == b_n:
        return True
    return SequenceMatcher(None, a_n, b_n).ratio() >= threshold


@dataclass
class MemoryStore:
    """
    Very small persistent memory to avoid sending repeats.

    - Exact duplicates: URL already sent.
    - Near-duplicates: same source + very similar title already sent.
    """

    path: str
    data: Dict

    @staticmethod
    def load(path: str) -> "MemoryStore":
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            return MemoryStore(path=path, data={"sent": [], "sent_by_source": {}, "sent_titles": [], "sent_texts": []})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        data.setdefault("sent", [])
        data.setdefault("sent_by_source", {})
        data.setdefault("sent_titles", [])
        data.setdefault("sent_texts", [])
        return MemoryStore(path=path, data=data)

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _sent_urls(self) -> set:
        return {x.get("url") for x in (self.data.get("sent") or []) if x.get("url")}

    def _sent_titles(self) -> set:
        return {_norm_title(t) for t in (self.data.get("sent_titles") or []) if t}

    def recent_sent_texts(self, limit: int = 80) -> List[str]:
        texts = [t for t in (self.data.get("sent_texts") or []) if isinstance(t, str) and t.strip()]
        return texts[-limit:]

    def should_skip(self, item: Item) -> bool:
        # Layer 1: exact title match (global).
        if _norm_title(item.title) in self._sent_titles():
            return True

        if item.url and item.url in self._sent_urls():
            return True

        titles: List[str] = (self.data.get("sent_by_source") or {}).get(item.source_name, []) or []
        for t in titles[-200:]:
            if _is_similar_title(item.title, t):
                return True
        return False

    def mark_sent(self, item: Item, *, sent_text: Optional[str] = None) -> None:
        sent = self.data.setdefault("sent", [])
        sent.append(
            {
                "at": _now_iso(),
                "source": item.source_name,
                "platform": item.platform,
                "title": item.title,
                "url": item.url,
            }
        )

        by_source = self.data.setdefault("sent_by_source", {})
        by_source.setdefault(item.source_name, []).append(item.title)

        titles = self.data.setdefault("sent_titles", [])
        titles.append(item.title)

        if sent_text:
            texts = self.data.setdefault("sent_texts", [])
            texts.append(_norm_text(sent_text))

        # Keep file bounded.
        self.data["sent"] = sent[-2000:]
        for k, v in list(by_source.items()):
            by_source[k] = (v or [])[-500:]
        self.data["sent_titles"] = (self.data.get("sent_titles") or [])[-3000:]
        self.data["sent_texts"] = (self.data.get("sent_texts") or [])[-1000:]


def filter_new_items(items: Iterable[Item], store: MemoryStore) -> List[Item]:
    out: List[Item] = []
    for it in items:
        if store.should_skip(it):
            continue
        out.append(it)
    return out

