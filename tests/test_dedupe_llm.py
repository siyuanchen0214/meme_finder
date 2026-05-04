from unittest.mock import MagicMock

import meme_finder.dedupe_llm as dedupe


def test_llm_should_send_no_api_key():
    send, reason = dedupe.llm_should_send(
        api_key=None,
        model="x",
        candidate_text="c",
        recent_texts=[],
    )
    assert send is True
    assert "disabled" in reason.lower()


def test_llm_should_send_parses_json(mocker):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content='{"send": false, "reason": "dup"}'))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    mocker.patch("openai.OpenAI", return_value=mock_client)

    send, reason = dedupe.llm_should_send(
        api_key="sk-x",
        model="m",
        candidate_text="c",
        recent_texts=["old"],
    )
    assert send is False
    assert reason == "dup"


def test_llm_should_send_invalid_json_fails_open(mocker):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="not json"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    mocker.patch("openai.OpenAI", return_value=mock_client)

    send, reason = dedupe.llm_should_send(
        api_key="sk-x",
        model="m",
        candidate_text="c",
        recent_texts=[],
    )
    assert send is True
    assert "parse failed" in reason.lower()
