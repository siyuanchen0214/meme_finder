import pytest

from meme_finder.config import (
    AppConfig,
    EmailConfig,
    load_config,
    load_email_from_env,
    load_sources_yaml,
)


def test_load_email_missing(monkeypatch):
    for k in [
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "EMAIL_FROM",
        "EMAIL_TO",
    ]:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="Missing required env vars"):
        load_email_from_env()


def test_load_email_strips_password_spaces(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "u@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "ab cd ef gh ij kl mn op")
    monkeypatch.setenv("EMAIL_FROM", "u@example.com")
    monkeypatch.setenv("EMAIL_TO", "v@example.com")
    cfg = load_email_from_env()
    assert cfg.smtp_password == "abcdefghijklmnop"


def test_load_sources_yaml_feed_only(tmp_path):
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
sources:
  - name: Blog
    platform: RSS
    feed_url: https://example.com/feed.xml
"""
    )
    srcs = load_sources_yaml(str(p))
    assert len(srcs) == 1
    assert srcs[0].feed_url == "https://example.com/feed.xml"


def test_load_sources_youtube_resolves_channel(mocker, tmp_path):
    mocker.patch(
        "meme_finder.config.resolve_channel_id",
        return_value="UCx5XG1OV2P6uZZ5FSM9Ttw",
    )
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
sources:
  - name: Ch
    platform: YouTube
    homepage_url: https://www.youtube.com/@Someone
"""
    )
    srcs = load_sources_yaml(str(p))
    assert len(srcs) == 1
    assert "channel_id=UCx5XG1OV2P6uZZ5FSM9Ttw" in srcs[0].feed_url


def test_load_sources_youtube_resolve_fails(mocker, tmp_path):
    mocker.patch("meme_finder.config.resolve_channel_id", return_value=None)
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
sources:
  - name: Ch
    platform: YouTube
    homepage_url: https://www.youtube.com/@bad
"""
    )
    with pytest.raises(RuntimeError, match="Could not resolve"):
        load_sources_yaml(str(p))


def test_load_config_no_email_when_dry_run(mocker, tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    p = tmp_path / "sources.yaml"
    p.write_text(
        """
sources:
  - name: Blog
    platform: RSS
    feed_url: https://example.com/feed.xml
"""
    )
    cfg = load_config(str(p), require_email=False)
    assert cfg.email is None
    assert isinstance(cfg, AppConfig)
