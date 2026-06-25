import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.video_gen import create_video, download_video, poll_until_complete


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-heygen-key")
    monkeypatch.setenv("HEYGEN_AVATAR_ID", "test-avatar-id")
    monkeypatch.setenv("HEYGEN_VOICE_ID", "test-voice-id")


# --- create_video ---

def test_create_video_returns_video_id():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"video_id": "abc-123"}}
    with patch("pipeline.video_gen.requests.post", return_value=mock_resp):
        result = create_video("Hello kids!")
    assert result == "abc-123"


def test_create_video_posts_correct_dimensions():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"video_id": "abc-123"}}
    with patch("pipeline.video_gen.requests.post", return_value=mock_resp) as mock_post:
        create_video("Hello kids!")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["dimension"] == {"width": 1080, "height": 1920}


def test_create_video_includes_idempotency_key():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"video_id": "abc-123"}}
    with patch("pipeline.video_gen.requests.post", return_value=mock_resp) as mock_post:
        create_video("Hello kids!")
    headers = mock_post.call_args.kwargs["headers"]
    assert "Idempotency-Key" in headers


# --- poll_until_complete ---

def test_poll_returns_url_on_completed():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"status": "completed", "video_url": "https://cdn.example.com/video.mp4"}
    }
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp), \
         patch("pipeline.video_gen.time.sleep"):
        url = poll_until_complete("abc-123")
    assert url == "https://cdn.example.com/video.mp4"


def test_poll_raises_runtime_error_on_failed():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "status": "failed",
            "failure_code": "AVATAR_NOT_FOUND",
            "failure_message": "Avatar does not exist",
        }
    }
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp), \
         patch("pipeline.video_gen.time.sleep"):
        with pytest.raises(RuntimeError, match="HeyGen render failed"):
            poll_until_complete("abc-123")


def test_poll_raises_timeout_when_deadline_exceeded():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"status": "processing"}}
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp), \
         patch("pipeline.video_gen.time.sleep"), \
         patch("pipeline.video_gen.POLL_TIMEOUT", -1):
        with pytest.raises(TimeoutError):
            poll_until_complete("abc-123")


# --- download_video ---

def test_download_video_writes_file_contents(tmp_path):
    dest = tmp_path / "video.mp4"
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp):
        result = download_video("https://example.com/video.mp4", dest)
    assert result == dest
    assert dest.read_bytes() == b"chunk1chunk2"


def test_download_video_creates_parent_dirs(tmp_path):
    dest = tmp_path / "subdir" / "nested" / "video.mp4"
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.iter_content.return_value = [b"data"]
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp):
        download_video("https://example.com/video.mp4", dest)
    assert dest.exists()
