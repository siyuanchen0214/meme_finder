from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

# OpenAI Whisper API upload limit (conservative).
_MAX_UPLOAD_BYTES = 24 * 1024 * 1024
_SEGMENT_SECONDS = 600  # 10 minutes


def _which_ffmpeg() -> Optional[str]:
    return shutil.which("ffmpeg")


def _run_ffmpeg_compact_mp3(src: str, dst: str) -> None:
    ffmpeg = _which_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is required to shrink/split large audio files. Install ffmpeg (e.g. `brew install ffmpeg`)."
        )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            src,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            dst,
        ],
        check=True,
        capture_output=True,
    )


def _run_ffmpeg_split_mp3(src: str, out_pattern: str) -> None:
    ffmpeg = _which_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg is required to split large audio files. Install ffmpeg (e.g. `brew install ffmpeg`)."
        )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            src,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            "-f",
            "segment",
            "-segment_time",
            str(_SEGMENT_SECONDS),
            "-reset_timestamps",
            "1",
            out_pattern,
        ],
        check=True,
        capture_output=True,
    )


def _transcribe_one_file(client, path: str, *, model: str) -> str:
    with open(path, "rb") as f:
        tr = client.audio.transcriptions.create(model=model, file=f)
    return (getattr(tr, "text", None) or "").strip()


def transcribe_file_with_openai(
    client,
    path: str,
    *,
    model: str = "whisper-1",
) -> str:
    """
    Transcribe a local audio file using OpenAI speech-to-text.
    Handles large inputs by compacting and/or segmenting with ffmpeg.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    size = os.path.getsize(path)
    if size <= _MAX_UPLOAD_BYTES:
        return _transcribe_one_file(client, path, model=model)

    with tempfile.TemporaryDirectory() as td:
        compact = os.path.join(td, "compact.mp3")
        _run_ffmpeg_compact_mp3(path, compact)
        if os.path.getsize(compact) <= _MAX_UPLOAD_BYTES:
            return _transcribe_one_file(client, compact, model=model)

        pattern = os.path.join(td, "part_%03d.mp3")
        _run_ffmpeg_split_mp3(compact, pattern)

        parts = sorted(Path(td).glob("part_*.mp3"))
        if not parts:
            raise RuntimeError("ffmpeg segmentation produced no output parts")

        texts: List[str] = []
        for p in parts:
            if p.stat().st_size > _MAX_UPLOAD_BYTES:
                raise RuntimeError(
                    "A single audio segment is still too large for the OpenAI transcription upload limit."
                )
            texts.append(_transcribe_one_file(client, str(p), model=model))

    return "\n".join(t for t in texts if t).strip()


def transcribe_youtube_url_openai(
    *,
    url: str,
    api_key: str,
    whisper_model: str = "whisper-1",
) -> str:
    """Download YouTube audio to a temp dir and transcribe with OpenAI."""
    from openai import OpenAI

    from .youtube_audio import download_youtube_best_audio

    client = OpenAI(api_key=api_key)
    with tempfile.TemporaryDirectory() as td:
        audio_path = download_youtube_best_audio(url, td)
        return transcribe_file_with_openai(client, audio_path, model=whisper_model)
