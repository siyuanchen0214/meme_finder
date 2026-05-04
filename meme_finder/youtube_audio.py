from __future__ import annotations

import os
from pathlib import Path


def download_youtube_best_audio(url: str, out_dir: str) -> str:
    """
    Download best-effort audio-only track for a YouTube URL into out_dir.
    Returns path to the downloaded media file.
    """
    try:
        import yt_dlp  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "yt-dlp is required for OpenAI audio transcription. "
            "Install dependencies: pip install -r requirements.txt"
        ) from e

    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    outtmpl = str(out_dir_p / "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "quiet": True,
        "noplaylist": True,
        "retries": 10,
        "fragment_retries": 10,
        # YouTube frequently returns 403 for the default web client; alternate clients are more reliable.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "ios"],
            }
        },
        # Prefer formats we can feed to ffmpeg/OpenAI without extra merge issues.
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        vid = str(info.get("id") or "")
        if not vid:
            raise RuntimeError("yt-dlp did not return a video id")

        # After FFmpegExtractAudio, output is typically .mp3
        mp3 = out_dir_p / f"{vid}.mp3"
        if mp3.is_file():
            return str(mp3)

        # Fallback: any file matching id
        matches = list(out_dir_p.glob(f"{vid}.*"))
        if not matches:
            raise RuntimeError("yt-dlp finished but no output file was found")
        return str(matches[0])
