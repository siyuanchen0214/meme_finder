from unittest.mock import MagicMock

from meme_finder.__main__ import build_parser, cmd_run_video


def test_run_video_dry_run_one_youtube_url(mocker, capsys):
    """One-item run-video path: title fetch, summarize with default STT mode, print digest (no email)."""
    mocker.patch("meme_finder.__main__.load_app_env")
    mocker.patch(
        "meme_finder.__main__.load_openai_from_env",
        return_value=MagicMock(api_key="sk-test", model="gpt-test", whisper_model="whisper-test"),
    )
    mocker.patch("meme_finder.__main__.fetch_youtube_oembed_title", return_value="Me at the zoo")
    mock_summarize = mocker.patch(
        "meme_finder.__main__.summarize_items",
        return_value=["- **Punchline:** elephants exist. **Link:** https://www.youtube.com/watch?v=jNQXAC9IVRw"],
    )

    p = build_parser()
    args = p.parse_args(
        [
            "run-video",
            "--url",
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "--dry-run",
        ]
    )
    assert cmd_run_video(args) == 0

    mock_summarize.assert_called_once()
    items_arg = mock_summarize.call_args.args[0]
    call_kw = mock_summarize.call_args.kwargs
    assert call_kw["transcription_mode"] == "openai_audio"
    assert call_kw["whisper_model"] == "whisper-test"
    assert len(items_arg) == 1
    assert items_arg[0].url == "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert items_arg[0].title == "Me at the zoo"

    out = capsys.readouterr().out
    assert "每日幽默精选" in out
    assert "jNQXAC9IVRw" in out
    assert "elephants" in out
