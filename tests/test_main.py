import json
import sys
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("HEYGEN_API_KEY", "test")
    monkeypatch.setenv("HEYGEN_AVATAR_ID", "test")
    monkeypatch.setenv("HEYGEN_VOICE_ID", "test")


FAKE_SCRIPT = {
    "title": "Why Stars Twinkle",
    "description": "A fun video about stars!",
    "tags": ["kids", "science", "stars"],
    "narration": "Stars are very far away!",
}


def test_main_calls_pipeline_in_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "why do stars twinkle"])

    with patch("main.script_gen.generate_script", return_value=FAKE_SCRIPT) as mock_gen, \
         patch("main.video_gen.create_video", return_value="vid-123") as mock_create, \
         patch("main.video_gen.poll_until_complete", return_value="https://ex.com/v.mp4") as mock_poll, \
         patch("main.video_gen.download_video") as mock_dl:
        import main
        main.main()

    mock_gen.assert_called_once_with("why do stars twinkle")
    mock_create.assert_called_once_with(FAKE_SCRIPT["narration"])
    mock_poll.assert_called_once_with("vid-123")
    mock_dl.assert_called_once()


def test_main_writes_sidecar_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "stars"])

    with patch("main.script_gen.generate_script", return_value=FAKE_SCRIPT), \
         patch("main.video_gen.create_video", return_value="vid-456"), \
         patch("main.video_gen.poll_until_complete", return_value="https://ex.com/v.mp4"), \
         patch("main.video_gen.download_video"):
        import main
        main.main()

    sidecar = tmp_path / "output" / "pending_review" / "vid-456.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["title"] == FAKE_SCRIPT["title"]
    assert data["topic"] == "stars"
    assert "generated_at" in data


def test_main_creates_output_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["main.py", "topic"])

    with patch("main.script_gen.generate_script", return_value=FAKE_SCRIPT), \
         patch("main.video_gen.create_video", return_value="vid-789"), \
         patch("main.video_gen.poll_until_complete", return_value="https://ex.com/v.mp4"), \
         patch("main.video_gen.download_video"):
        import main
        main.main()

    assert (tmp_path / "output" / "pending_review").is_dir()
    assert (tmp_path / "output" / "approved").is_dir()
