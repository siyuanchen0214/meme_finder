from unittest.mock import MagicMock

import meme_finder.youtube as yt


def test_youtube_rss_url():
    assert (
        yt.youtube_rss_from_channel_id("UCx5XG1OV2P6uZZ5FSM9Ttw")
        == "https://www.youtube.com/feeds/videos.xml?channel_id=UCx5XG1OV2P6uZZ5FSM9Ttw"
    )


def test_resolve_channel_id_from_browse_id(mocker):
    cid = "UCx5XG1OV2P6uZZ5FSM9Ttw"
    resp = MagicMock()
    resp.status_code = 200
    resp.text = f'junk "browseId":"{cid}" more'
    mocker.patch("meme_finder.youtube.requests.get", return_value=resp)
    assert yt.resolve_channel_id("https://www.youtube.com/@x") == cid


def test_resolve_channel_id_non_200(mocker):
    resp = MagicMock()
    resp.status_code = 404
    mocker.patch("meme_finder.youtube.requests.get", return_value=resp)
    assert yt.resolve_channel_id("https://www.youtube.com/@x") is None
