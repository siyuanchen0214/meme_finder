import sys

from meme_finder.__main__ import main


def test_cli_test_email(mocker, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "h")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "u@u.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("EMAIL_FROM", "u@u.com")
    monkeypatch.setenv("EMAIL_TO", "v@v.com")
    mocker.patch("meme_finder.__main__.load_app_env")
    mock_send = mocker.patch("meme_finder.__main__.send_email")

    monkeypatch.setattr(sys, "argv", ["meme_finder", "test-email", "--message", "hello"])
    assert main() == 0
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert "hello" in kwargs["body_markdown"]


def test_cli_run_dry_run_empty_fetch(mocker, monkeypatch, tmp_path, capsys):
    yaml = tmp_path / "sources.yaml"
    yaml.write_text(
        """
sources:
  - name: A
    platform: RSS
    feed_url: https://example.com/feed.xml
"""
    )
    state = tmp_path / "memory.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "meme_finder",
            "run",
            "--sources",
            str(yaml),
            "--dry-run",
            "--state-path",
            str(state),
            "--min-items",
            "1",
            "--max-items",
            "2",
        ],
    )
    mocker.patch("meme_finder.__main__.fetch_all", return_value=[])
    mocker.patch("meme_finder.__main__.summarize_items", return_value=[])

    assert main() == 0
    out = capsys.readouterr().out
    assert "每日幽默精选" in out
