from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import yaml
from dotenv import load_dotenv

from .types import Source
from .youtube import resolve_channel_id, youtube_rss_from_channel_id


def load_app_env() -> None:
    """Load `MEME_FINDER_DOTENV` if set, else `.env` in the current working directory."""
    override = os.getenv("MEME_FINDER_DOTENV")
    path = override or ".env"
    if path and os.path.isfile(path):
        load_dotenv(path)
        return
    load_dotenv()


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_from: str
    email_to: str


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: Optional[str]
    model: str = "gpt-4o-mini"
    whisper_model: str = "whisper-1"


@dataclass(frozen=True)
class AppConfig:
    sources: List[Source]
    email: Optional[EmailConfig]
    openai: OpenAIConfig


def load_sources_yaml(path: str) -> List[Source]:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    sources = []
    for s in (raw.get("sources") or []):
        homepage_url = s.get("homepage_url") or s.get("url")
        feed_url = s.get("feed_url")

        # Convenience: allow specifying a YouTube channel URL/handle instead of channel_id RSS.
        if not feed_url and str(s.get("platform", "")).lower() == "youtube" and homepage_url:
            channel_id = resolve_channel_id(str(homepage_url))
            if not channel_id:
                raise RuntimeError(f"Could not resolve YouTube channel_id for: {homepage_url}")
            feed_url = youtube_rss_from_channel_id(channel_id)

        if not feed_url:
            raise RuntimeError(f"Missing feed_url for source: {s.get('name')}")

        sources.append(
            Source(
                name=str(s["name"]),
                platform=str(s.get("platform", "RSS")),
                feed_url=str(feed_url),
                homepage_url=str(homepage_url) if homepage_url else None,
            )
        )
    return sources


def load_email_from_env() -> EmailConfig:
    missing = [k for k in ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"] if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars for email: {', '.join(missing)}")

    # Gmail app passwords are often copied with spaces; SMTP expects 16 chars without them.
    smtp_password = os.environ["SMTP_PASSWORD"].replace(" ", "").strip()

    return EmailConfig(
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ["SMTP_PORT"]),
        smtp_username=os.environ["SMTP_USERNAME"],
        smtp_password=smtp_password,
        email_from=os.environ["EMAIL_FROM"],
        email_to=os.environ["EMAIL_TO"],
    )


def load_openai_from_env() -> OpenAIConfig:
    return OpenAIConfig(
        api_key=(os.getenv("OPENAI_API_KEY") or "").strip() or None,
        model=os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
        whisper_model=os.getenv("OPENAI_WHISPER_MODEL") or "whisper-1",
    )


def load_zhihu_secret_from_env() -> str:
    secret = (os.getenv("ZHIHU_ACCESS_SECRET") or "").strip()
    if not secret:
        raise RuntimeError(
            "Missing ZHIHU_ACCESS_SECRET. Add it to your .env "
            "(get it from developer.zhihu.com 个人中心)."
        )
    return secret


def load_config(sources_path: str, *, require_email: bool = True) -> AppConfig:
    return AppConfig(
        sources=load_sources_yaml(sources_path),
        email=load_email_from_env() if require_email else None,
        openai=load_openai_from_env(),
    )

