"""知乎去重库：记录“已推送过”的内容，避免重复推送。

设计目标：
- **纯 Python 精确/指纹去重，零 LLM token 成本**。
- 存本地 JSON（默认 `.state/zhihu_seen.json`）；在 GitHub Actions 里可随文档一起
  commit 回仓库，从而跨天持久（相当于一个“云端 set”）。

去重两层（都不花钱）：
1. 主键 key：`ContentID`（知乎稳定内容 ID），没有就用去掉 utm 的 URL。
2. 指纹 fingerprint：`标题 + 正文前 N 字` 归一化后的 sha1，用于抓“同内容换了链接重发”的近重复。

可独立运行做测试：
    python -m meme_finder.zhihu_seen --path .state/zhihu_seen.json --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

# 只在类型检查/取属性时用；运行时对任何有这些属性的对象都适用（鸭子类型）。
_FINGERPRINT_PREFIX_CHARS = 60
_MAX_KEYS = 8000
_MAX_FINGERPRINTS = 8000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def item_key(item) -> str:
    """稳定主键：优先 ContentID，其次去 utm 的 URL，最后标题。"""
    cid = getattr(item, "content_id", "") or ""
    if cid:
        return f"cid:{cid}"
    url = getattr(item, "clean_url", "") or getattr(item, "url", "") or ""
    if url:
        return f"url:{url}"
    return "title:" + _norm(getattr(item, "title", ""))


def item_fingerprint(item) -> str:
    """内容指纹：标题 + 正文前 N 字，归一化后 sha1。抓“换链接重发”的近重复。"""
    title = _norm(getattr(item, "title", ""))
    text = _norm(getattr(item, "content_text", ""))[:_FINGERPRINT_PREFIX_CHARS]
    raw = f"{title}|{text}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


@dataclass
class SeenStore:
    path: str
    keys: Set[str] = field(default_factory=set)
    fingerprints: Set[str] = field(default_factory=set)
    # 保留顺序用于裁剪（近似 FIFO）。
    _key_order: List[str] = field(default_factory=list)
    _fp_order: List[str] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "SeenStore":
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        if not os.path.exists(path):
            return cls(path=path, meta={"created_at": _now_iso()})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        key_order = list(data.get("keys") or [])
        fp_order = list(data.get("fingerprints") or [])
        return cls(
            path=path,
            keys=set(key_order),
            fingerprints=set(fp_order),
            _key_order=key_order,
            _fp_order=fp_order,
            meta=data.get("meta") or {},
        )

    def save(self) -> None:
        self.meta["updated_at"] = _now_iso()
        self.meta["count"] = len(self.keys)
        payload = {
            "keys": self._key_order,
            "fingerprints": self._fp_order,
            "meta": self.meta,
        }
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def is_seen(self, item) -> bool:
        return item_key(item) in self.keys or item_fingerprint(item) in self.fingerprints

    def mark(self, item) -> None:
        k = item_key(item)
        if k not in self.keys:
            self.keys.add(k)
            self._key_order.append(k)
        fp = item_fingerprint(item)
        if fp not in self.fingerprints:
            self.fingerprints.add(fp)
            self._fp_order.append(fp)

    def prune(self) -> None:
        if len(self._key_order) > _MAX_KEYS:
            self._key_order = self._key_order[-_MAX_KEYS:]
            self.keys = set(self._key_order)
        if len(self._fp_order) > _MAX_FINGERPRINTS:
            self._fp_order = self._fp_order[-_MAX_FINGERPRINTS:]
            self.fingerprints = set(self._fp_order)


def filter_unseen(items: List, store: Optional[SeenStore]) -> List:
    """返回未推送过的条目（保持原顺序）。store 为 None 时原样返回。"""
    if store is None:
        return list(items)
    out = []
    for it in items:
        if store.is_seen(it):
            continue
        out.append(it)
    return out


def _main() -> int:
    p = argparse.ArgumentParser(description="知乎去重库工具（查看/重置）。")
    p.add_argument("--path", default=".state/zhihu_seen.json")
    p.add_argument("--stats", action="store_true", help="打印当前已记录的数量。")
    p.add_argument("--reset", action="store_true", help="清空去重库。")
    args = p.parse_args()

    if args.reset:
        store = SeenStore(path=args.path, meta={"created_at": _now_iso()})
        store.save()
        print(f"Reset seen store at {args.path}")
        return 0

    store = SeenStore.load(args.path)
    print(f"path: {store.path}")
    print(f"keys: {len(store.keys)}")
    print(f"fingerprints: {len(store.fingerprints)}")
    print(f"meta: {store.meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
