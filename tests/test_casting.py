import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-heygen-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")


AVATARS_RESPONSE = {
    "data": {
        "avatars": [
            {"avatar_id": "av-1", "avatar_name": "Friendly Teacher", "gender": "female"},
            {"avatar_id": "av-2", "avatar_name": "Cool Scientist", "gender": "male"},
        ]
    }
}

VOICES_RESPONSE = {
    "data": {
        "voices": [
            {"voice_id": "vo-en-1", "name": "Cheerful Anna", "language": "English", "gender": "female"},
            {"voice_id": "vo-es-1", "name": "Carlos", "language": "Spanish", "gender": "male"},
            {"voice_id": "vo-en-2", "name": "Warm Ben", "language": "English", "gender": "male"},
        ]
    }
}

SCRIPT = {
    "title": "Why Do Stars Twinkle?",
    "narration": "Stars are far away and twinkle because of the air!",
    "tags": ["kids", "science", "stars"],
    "description": "A fun space video",
}


def _mock_get(url, **kwargs):
    resp = MagicMock()
    if "avatars" in url:
        resp.json.return_value = AVATARS_RESPONSE
    else:
        resp.json.return_value = VOICES_RESPONSE
    return resp


def _mock_claude_message(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(data))]
    return msg


def test_list_avatars_normalizes_fields():
    with patch("pipeline.casting.requests.get", side_effect=_mock_get):
        from pipeline.casting import list_avatars
        avatars = list_avatars()
    assert avatars == [
        {"avatar_id": "av-1", "name": "Friendly Teacher", "gender": "female"},
        {"avatar_id": "av-2", "name": "Cool Scientist", "gender": "male"},
    ]


def test_list_voices_normalizes_fields():
    with patch("pipeline.casting.requests.get", side_effect=_mock_get):
        from pipeline.casting import list_voices
        voices = list_voices()
    assert {"voice_id": "vo-en-1", "name": "Cheerful Anna", "language": "English", "gender": "female"} in voices
    assert len(voices) == 3


def test_select_cast_returns_claude_choice_when_valid():
    with patch("pipeline.casting.requests.get", side_effect=_mock_get), \
         patch("pipeline.casting.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _mock_claude_message(
            {"avatar_id": "av-2", "voice_id": "vo-en-2"}
        )
        from pipeline.casting import select_cast
        cast = select_cast(SCRIPT)
    assert cast == {"avatar_id": "av-2", "voice_id": "vo-en-2"}


def test_select_cast_filters_non_english_voices_from_claude_input():
    with patch("pipeline.casting.requests.get", side_effect=_mock_get), \
         patch("pipeline.casting.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _mock_claude_message(
            {"avatar_id": "av-1", "voice_id": "vo-en-1"}
        )
        from pipeline.casting import select_cast
        select_cast(SCRIPT)
        user_content = MockClient.return_value.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "vo-es-1" not in user_content
    assert "vo-en-1" in user_content


def test_select_cast_falls_back_on_invalid_claude_id():
    with patch("pipeline.casting.requests.get", side_effect=_mock_get), \
         patch("pipeline.casting.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _mock_claude_message(
            {"avatar_id": "does-not-exist", "voice_id": "also-fake"}
        )
        from pipeline.casting import select_cast
        cast = select_cast(SCRIPT)
    # falls back to first available avatar and first available ENGLISH voice
    assert cast["avatar_id"] == "av-1"
    assert cast["voice_id"] == "vo-en-1"


def test_select_cast_raises_when_no_avatars():
    empty = {"data": {"avatars": []}}

    def get_empty(url, **kwargs):
        resp = MagicMock()
        resp.json.return_value = empty if "avatars" in url else VOICES_RESPONSE
        return resp

    with patch("pipeline.casting.requests.get", side_effect=get_empty), \
         patch("pipeline.casting.anthropic.Anthropic"):
        from pipeline.casting import select_cast
        with pytest.raises(RuntimeError):
            select_cast(SCRIPT)
