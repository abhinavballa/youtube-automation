import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def env_vars(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRETS_PATH", "/fake/client_secrets.json")


METADATA = {
    "title": "Why Do Stars Twinkle?",
    "description": "Learn about stars in this fun video for kids!",
    "tags": ["kids", "science", "stars"],
}


def test_upload_video_returns_youtube_url(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake video data")

    mock_creds = MagicMock()
    mock_creds.valid = True

    mock_response = {"id": "dQw4w9WgXcQ"}
    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.side_effect = [(None, None), (None, mock_response)]

    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_req

    with patch("pipeline.youtube_upload._get_credentials", return_value=mock_creds), \
         patch("pipeline.youtube_upload.googleapiclient.discovery.build", return_value=mock_youtube), \
         patch("pipeline.youtube_upload.googleapiclient.http.MediaFileUpload"):
        from pipeline.youtube_upload import upload_video
        url = upload_video(video_path, METADATA, "2026-01-15T18:00:00Z")

    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_upload_video_sets_correct_body(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")

    mock_insert_req = MagicMock()
    mock_insert_req.next_chunk.side_effect = [(None, {"id": "abc"})]

    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_req

    with patch("pipeline.youtube_upload._get_credentials", return_value=MagicMock()), \
         patch("pipeline.youtube_upload.googleapiclient.discovery.build", return_value=mock_youtube), \
         patch("pipeline.youtube_upload.googleapiclient.http.MediaFileUpload"):
        from pipeline.youtube_upload import upload_video
        upload_video(video_path, METADATA, "2026-01-15T18:00:00Z")

    body = mock_youtube.videos.return_value.insert.call_args.kwargs["body"]
    assert body["snippet"]["title"] == METADATA["title"]
    assert body["snippet"]["categoryId"] == "27"
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2026-01-15T18:00:00Z"


def test_get_credentials_returns_valid_cached_token(tmp_path):
    token_data = {
        "token": "access-token",
        "refresh_token": "refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
    }
    token_file = tmp_path / ".youtube_token.json"
    token_file.write_text(json.dumps(token_data))

    mock_creds = MagicMock()
    mock_creds.valid = True

    with patch("pipeline.youtube_upload.TOKEN_PATH", token_file), \
         patch("pipeline.youtube_upload.Credentials.from_authorized_user_file", return_value=mock_creds):
        from pipeline.youtube_upload import _get_credentials
        creds = _get_credentials()

    assert creds is mock_creds
