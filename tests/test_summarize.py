from unittest.mock import MagicMock

from meme_finder.summarize import summarize_items
from meme_finder.types import Item


def _item():
    return Item(
        source_name="Src",
        platform="YouTube",
        title="A funny title",
        url="https://www.youtube.com/watch?v=abc",
        published_at=None,
    )


def test_summarize_fallback_without_api_key():
    blocks = summarize_items([_item()], api_key=None, model="gpt-4")
    assert len(blocks) == 1
    assert "A funny title" in blocks[0]
    assert "https://www.youtube.com/watch?v=abc" in blocks[0]


def test_summarize_openai_appends_link_if_missing(mocker):
    mocker.patch("meme_finder.summarize.get_transcript_text", return_value=None)
    mocker.patch(
        "meme_finder.summarize.build_llm_document",
        return_value="Title: x\nSource: y\nURL: https://www.youtube.com/watch?v=abc\nstub",
    )
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Just text."))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    mocker.patch("openai.OpenAI", return_value=mock_client)

    it = _item()
    blocks = summarize_items([it], api_key="sk-test", model="gpt-test")
    assert len(blocks) == 1
    assert "Just text." in blocks[0]
    assert it.url in blocks[0]


def test_summarize_openai_empty_response_falls_back(mocker):
    mocker.patch("meme_finder.summarize.get_transcript_text", return_value=None)
    mocker.patch("meme_finder.summarize.build_llm_document", return_value="stub doc")
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=""))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    mocker.patch("openai.OpenAI", return_value=mock_client)

    it = _item()
    blocks = summarize_items([it], api_key="sk-test", model="gpt-test")
    assert it.url in blocks[0]
