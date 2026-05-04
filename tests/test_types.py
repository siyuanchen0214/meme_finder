from datetime import datetime, timezone

from meme_finder.types import Item, Source


def test_source_frozen():
    s = Source(name="n", platform="YouTube", feed_url="https://example.com/feed")
    assert s.name == "n"
    assert s.homepage_url is None


def test_item_optional_summary():
    it = Item(
        source_name="A",
        platform="RSS",
        title="T",
        url="https://u",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert it.summary is None
