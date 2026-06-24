import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def _make_mock_message(data: dict) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(data))]
    return msg


VALID_PAYLOAD = {
    "narration": "Stars twinkle because of the atmosphere!",
    "title": "Why Do Stars Twinkle?",
    "description": "Learn about stars in this fun video for kids!",
    "tags": ["kids", "science", "stars"],
}


def test_generate_script_returns_parsed_dict():
    with patch("pipeline.script_gen.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _make_mock_message(VALID_PAYLOAD)
        from pipeline.script_gen import generate_script
        result = generate_script("why do stars twinkle")
    assert result == VALID_PAYLOAD


def test_generate_script_uses_correct_model():
    with patch("pipeline.script_gen.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _make_mock_message(VALID_PAYLOAD)
        from pipeline.script_gen import generate_script
        generate_script("topic")
    kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"


def test_generate_script_raises_on_invalid_json():
    msg = MagicMock()
    msg.content = [MagicMock(text="this is not json")]
    with patch("pipeline.script_gen.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = msg
        from pipeline.script_gen import generate_script
        with pytest.raises(ValueError, match="not valid JSON"):
            generate_script("topic")


def test_generate_script_raises_on_missing_keys():
    incomplete = {"narration": "hello", "title": "Hi"}
    with patch("pipeline.script_gen.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = _make_mock_message(incomplete)
        from pipeline.script_gen import generate_script
        with pytest.raises(ValueError, match="missing required keys"):
            generate_script("topic")
