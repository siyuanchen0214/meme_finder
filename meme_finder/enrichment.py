"""
Build the text blob we pass to the LLM for each Item.

Extension point: richer extraction should live here (captions vs OpenAI STT vs future sources).
Downstream summarization/email formatting should not hardcode YouTube-specific details.
"""

from __future__ import annotations

import re
from typing import List, Optional

import requests

from .types import Item

# Prefer captions the comedy channels often have.
_DEFAULT_TRANSCRIPT_LANGS: List[str] = ["zh-Hans", "zh-Hant", "zh", "en"]


def get_youtube_video_id(url: str) -> Optional[str]:
    if not url:
        return None
    patterns = [
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"[?&]v=([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _is_youtube_item(item: Item) -> bool:
    u = (item.url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return True
    return str(item.platform).lower() == "youtube"


def fetch_youtube_oembed_title(url: str, *, timeout_s: int = 15) -> Optional[str]:
    try:
        r = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=timeout_s,
            headers={"User-Agent": "meme_finder/0.1"},
        )
        if r.status_code != 200:
            return None
        return (r.json().get("title") or "").strip() or None
    except Exception:
        return None


def fetch_youtube_transcript_text(
    video_id: str,
    *,
    max_chars: Optional[int] = 48_000,
    languages: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Returns plain transcript text, or None if unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception:
        return None

    langs = languages or _DEFAULT_TRANSCRIPT_LANGS
    try:
        chunks = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
    except Exception:
        try:
            chunks = YouTubeTranscriptApi.get_transcript(video_id)
        except Exception:
            return None

    parts = [c.get("text", "") for c in chunks if isinstance(c, dict)]
    text = " ".join(parts).strip()
    if not text:
        return None

    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Transcript truncated for length.]"
    return text


def _prefix_source(text: str, source: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    return f"[Transcript source: {source}]\n\n{t}"


def transcript_body_for_model(transcript: Optional[str]) -> str:
    """Strip the leading source banner so chunking/tokenization sees raw dialogue."""
    if not transcript:
        return ""
    if transcript.startswith("[Transcript source:") and "\n\n" in transcript:
        return transcript.split("\n\n", 1)[1].strip()
    return transcript.strip()


def get_transcript_text(
    item: Item,
    *,
    use_transcript: bool = True,
    max_transcript_chars: Optional[int] = 48_000,
    transcription_mode: str = "auto",
    openai_api_key: Optional[str] = None,
    whisper_model: str = "whisper-1",
) -> Optional[str]:
    """
    transcription_mode:
      - captions: YouTube captions only
      - openai_audio: download audio + OpenAI speech-to-text (full video, chunked if needed)
      - auto: captions first; if missing/too short, fall back to openai_audio when api key exists
    """
    if not use_transcript or not _is_youtube_item(item):
        return None
    vid = get_youtube_video_id(item.url)
    if not vid:
        return None

    def _truncate(s: str) -> str:
        if max_transcript_chars is None:
            return s
        if len(s) <= max_transcript_chars:
            return s
        return s[: max_transcript_chars] + "\n\n[Transcript truncated for length.]"

    mode = (transcription_mode or "auto").lower().strip()

    if mode == "captions":
        cap = fetch_youtube_transcript_text(vid, max_chars=max_transcript_chars, languages=_DEFAULT_TRANSCRIPT_LANGS)
        if not cap:
            return None
        return _prefix_source(cap, "YouTube captions")

    if mode == "openai_audio":
        if not openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for transcription_mode=openai_audio")
        from .openai_transcribe import transcribe_youtube_url_openai

        stt = transcribe_youtube_url_openai(
            url=item.url,
            api_key=openai_api_key,
            whisper_model=whisper_model,
        )
        if not stt:
            return None
        return _prefix_source(_truncate(stt), "OpenAI speech-to-text")

    # auto
    cap = fetch_youtube_transcript_text(vid, max_chars=max_transcript_chars, languages=_DEFAULT_TRANSCRIPT_LANGS)
    if cap and len(cap.strip()) >= 400:
        return _prefix_source(cap, "YouTube captions")

    if openai_api_key:
        from .openai_transcribe import transcribe_youtube_url_openai

        stt = transcribe_youtube_url_openai(
            url=item.url,
            api_key=openai_api_key,
            whisper_model=whisper_model,
        )
        if stt:
            return _prefix_source(_truncate(stt), "OpenAI speech-to-text")
    return None


def build_llm_document(
    item: Item,
    *,
    use_transcript: bool = True,
    max_transcript_chars: Optional[int] = 48_000,
    transcription_mode: str = "auto",
    openai_api_key: Optional[str] = None,
    whisper_model: str = "whisper-1",
) -> str:
    """
    Single string handed to the summarizer as the "source material" for this item.
    Replace implementation / add branches here when you upgrade extraction.
    """
    lines = [
        f"Title: {item.title}",
        f"Source: {item.source_name}",
        f"Platform: {item.platform}",
        f"URL: {item.url}",
        f"Feed snippet (RSS / metadata): {item.summary or '(none)'}",
    ]

    transcript_block = get_transcript_text(
        item,
        use_transcript=use_transcript,
        max_transcript_chars=max_transcript_chars,
        transcription_mode=transcription_mode,
        openai_api_key=openai_api_key,
        whisper_model=whisper_model,
    )

    if transcript_block:
        lines.append("")
        lines.append("Video transcript:")
        lines.append(transcript_block)
    else:
        lines.append("")
        lines.append(
            "Video transcript: (not available or skipped — summarizing from title/snippet only.)"
        )

    return "\n".join(lines)
