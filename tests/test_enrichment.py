from meme_finder.enrichment import (
    build_llm_document,
    get_transcript_text,
    get_youtube_video_id,
    transcript_body_for_model,
)
from meme_finder.types import Item


def test_get_youtube_video_id_watch():
    assert (
        get_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_get_youtube_video_id_short():
    assert get_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_build_llm_document_skips_transcript_when_disabled():
    it = Item(
        source_name="S",
        platform="YouTube",
        title="T",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        published_at=None,
        summary="snip",
    )
    doc = build_llm_document(it, use_transcript=False)
    assert "not available or skipped" in doc
    assert "Video transcript (caption-derived" not in doc


def test_build_llm_document_with_mocked_transcript(mocker):
    mocker.patch("meme_finder.enrichment.fetch_youtube_transcript_text", return_value="hello bit one. hello bit two.")
    it = Item(
        source_name="S",
        platform="YouTube",
        title="T",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        published_at=None,
    )
    doc = build_llm_document(it, use_transcript=True, transcription_mode="captions")
    assert "hello bit one" in doc
    assert "YouTube captions" in doc


def test_transcript_body_for_model_strips_banner():
    raw = "[Transcript source: X]\n\nhello world"
    assert transcript_body_for_model(raw) == "hello world"


def test_get_transcript_openai_audio(mocker):
    mocker.patch(
        "meme_finder.openai_transcribe.transcribe_youtube_url_openai",
        return_value="full stt text " * 200,
    )
    it = Item(
        source_name="S",
        platform="YouTube",
        title="T",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        published_at=None,
    )
    out = get_transcript_text(
        it,
        transcription_mode="openai_audio",
        openai_api_key="sk-test",
        max_transcript_chars=None,
    )
    assert out is not None
    assert "OpenAI speech-to-text" in out
