from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from meme_finder.fetch_rss import fetch_items_for_source
from meme_finder.types import Source


def test_fetch_items_newest_first(mocker):
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    older = now - timedelta(days=1)
    since = now - timedelta(hours=48)

    mocker.patch(
        "meme_finder.fetch_rss.feedparser.parse",
        return_value=SimpleNamespace(
            entries=[
                {"title": "Old", "link": "https://o", "published": older.isoformat()},
                {"title": "New", "link": "https://n", "published": now.isoformat()},
            ]
        ),
    )
    src = Source(name="S", platform="RSS", feed_url="http://feed")
    items = fetch_items_for_source(src, since=since)
    titles = [i.title for i in items]
    assert titles[0] == "New"
    assert titles[1] == "Old"


def test_fetch_items_drops_before_since(mocker):
    now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=30)
    since = now - timedelta(hours=24)

    mocker.patch(
        "meme_finder.fetch_rss.feedparser.parse",
        return_value=SimpleNamespace(
            entries=[
                {"title": "Too old", "link": "https://o", "published": old.isoformat()},
            ]
        ),
    )
    src = Source(name="S", platform="RSS", feed_url="http://feed")
    items = fetch_items_for_source(src, since=since)
    assert items == []
