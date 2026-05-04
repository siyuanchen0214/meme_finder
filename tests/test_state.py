import json
from datetime import datetime, timezone

from meme_finder.state import MemoryStore, filter_new_items
from meme_finder.types import Item


def _item(title="T", url="https://x", source="S"):
    return Item(
        source_name=source,
        platform="YouTube",
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc),
    )


def test_memory_roundtrip(tmp_path):
    p = tmp_path / "st" / "mem.json"
    store = MemoryStore.load(str(p))
    store.mark_sent(_item(), sent_text="summary one")
    store.save()

    store2 = MemoryStore.load(str(p))
    assert len(store2.data["sent"]) == 1
    assert store2.data["sent_titles"]


def test_skip_exact_title_globally(tmp_path):
    p = tmp_path / "m.json"
    store = MemoryStore.load(str(p))
    store.mark_sent(_item(title="Hello World"))
    assert store.should_skip(_item(title="hello  world", url="https://other"))


def test_skip_same_url(tmp_path):
    p = tmp_path / "m.json"
    store = MemoryStore.load(str(p))
    store.mark_sent(_item(url="https://same"))
    assert store.should_skip(_item(title="different title", url="https://same"))


def test_filter_new_items_order(tmp_path):
    p = tmp_path / "m.json"
    store = MemoryStore.load(str(p))
    a, b, c = _item("a", "https://1"), _item("b", "https://2"), _item("c", "https://3")
    out = filter_new_items([a, b, c], store)
    assert [x.title for x in out] == ["a", "b", "c"]


def test_recent_sent_texts_limit(tmp_path):
    p = tmp_path / "m.json"
    store = MemoryStore.load(str(p))
    for i in range(5):
        store.mark_sent(_item(title=f"t{i}", url=f"https://{i}"), sent_text=f"text{i}")
    recent = store.recent_sent_texts(limit=3)
    assert recent == ["text2", "text3", "text4"]
