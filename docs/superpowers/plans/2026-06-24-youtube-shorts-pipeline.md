# YouTube Shorts Kids' Education Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI pipeline that generates a kids' educational YouTube Short end-to-end: Claude script → HeyGen video → human review checkpoint → YouTube upload with scheduled private publish.

**Architecture:** Seven files across `pipeline/` (three modules), `main.py`, `approve.py`, `conftest.py`, plus config files. Data flows through the filesystem; a JSON sidecar alongside each video persists title/description/tags between the two separate pipeline invocations (generate and upload).

**Tech Stack:** Python 3.10+, `anthropic` SDK, `requests`, `tenacity`, `python-dotenv`, `google-api-python-client`, `google-auth-oauthlib`, `pytest`.

---

## File Map

| File | Responsibility |
|---|---|
| `pipeline/__init__.py` | Package marker |
| `pipeline/script_gen.py` | Claude haiku-4-5 → narration, title, description, tags |
| `pipeline/video_gen.py` | HeyGen create + poll + download |
| `pipeline/youtube_upload.py` | YouTube Data API v3 OAuth2 upload + CLI entrypoint |
| `main.py` | CLI orchestrator: runs steps 1-2, writes sidecar, stops for review |
| `approve.py` | CLI helper: moves video+sidecar from pending_review to approved |
| `conftest.py` | Adds project root to sys.path for test imports |
| `tests/test_script_gen.py` | Unit tests for script_gen |
| `tests/test_video_gen.py` | Unit tests for video_gen |
| `tests/test_youtube_upload.py` | Unit tests for youtube_upload |
| `tests/test_main.py` | Unit tests for main orchestrator |
| `tests/test_approve.py` | Unit tests for approve helper |
| `requirements.txt` | Runtime + test dependencies |
| `.env.example` | All required env var names with placeholder values |
| `.gitignore` | Excludes secrets, output/, caches |
| `README.md` | Setup and usage instructions |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pipeline/__init__.py`
- Create: `conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
# Core
anthropic
requests
tenacity
python-dotenv
google-api-python-client
google-auth-oauthlib
google-auth-httplib2

# Testing
pytest
```

- [ ] **Step 2: Create .env.example**

```
# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# HeyGen API
HEYGEN_API_KEY=your_heygen_api_key_here
HEYGEN_AVATAR_ID=your_avatar_id_here
HEYGEN_VOICE_ID=your_voice_id_here

# YouTube OAuth2
YOUTUBE_CLIENT_SECRETS_PATH=/path/to/client_secrets.json
```

- [ ] **Step 3: Create .gitignore**

```
.env
.youtube_token.json
client_secrets.json
output/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
venv/
.venv/
```

- [ ] **Step 4: Create pipeline/__init__.py**

Empty file — marks `pipeline/` as a Python package.

- [ ] **Step 5: Create conftest.py at project root**

```python
import sys
from pathlib import Path

root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
```

- [ ] **Step 6: Create tests/__init__.py**

Empty file.

- [ ] **Step 7: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore pipeline/__init__.py conftest.py tests/__init__.py
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: script_gen.py

**Files:**
- Create: `tests/test_script_gen.py`
- Create: `pipeline/script_gen.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_script_gen.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_script_gen.py -v
```

Expected: `ModuleNotFoundError` — `pipeline/script_gen.py` does not exist yet.

- [ ] **Step 3: Implement pipeline/script_gen.py**

```python
import json
import os

import anthropic

SYSTEM_PROMPT = """\
You are a scriptwriter for a kids' educational YouTube Shorts channel.
Write a 45-60 second narration script for a single on-screen presenter/avatar to read aloud.
The narration should be engaging, simple, and educational for children aged 5-10.

Return ONLY a valid JSON object with exactly these keys:
- "narration": the full narration text the avatar will speak (string)
- "title": a catchy YouTube video title (string, max 100 characters)
- "description": a 1-2 sentence YouTube video description (string)
- "tags": a list of 3-5 relevant tags (list of strings)

Return only the JSON object. No markdown, no code fences, no other text.\
"""


def generate_script(topic: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Topic: {topic}"}],
    )
    text = message.content[0].text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude response is not valid JSON: {exc}\nResponse: {text}") from exc

    required = {"narration", "title", "description", "tags"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Claude response missing required keys: {missing}")
    if not isinstance(data["tags"], list) or not (3 <= len(data["tags"]) <= 5):
        raise ValueError(f"tags must be a list of 3-5 items, got: {data['tags']}")

    return data
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_script_gen.py -v
```

Expected:
```
tests/test_script_gen.py::test_generate_script_returns_parsed_dict PASSED
tests/test_script_gen.py::test_generate_script_uses_correct_model PASSED
tests/test_script_gen.py::test_generate_script_raises_on_invalid_json PASSED
tests/test_script_gen.py::test_generate_script_raises_on_missing_keys PASSED
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/script_gen.py tests/test_script_gen.py
git commit -m "feat: add script_gen module (Claude haiku-4-5)"
```

---

## Task 3: video_gen.py

**Files:**
- Create: `tests/test_video_gen.py`
- Create: `pipeline/video_gen.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_video_gen.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


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
        from pipeline.video_gen import create_video
        result = create_video("Hello kids!")
    assert result == "abc-123"


def test_create_video_posts_correct_dimensions():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"video_id": "abc-123"}}
    with patch("pipeline.video_gen.requests.post", return_value=mock_resp) as mock_post:
        from pipeline.video_gen import create_video
        create_video("Hello kids!")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["dimension"] == {"width": 1080, "height": 1920}


def test_create_video_includes_idempotency_key():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"video_id": "abc-123"}}
    with patch("pipeline.video_gen.requests.post", return_value=mock_resp) as mock_post:
        from pipeline.video_gen import create_video
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
        from pipeline.video_gen import poll_until_complete
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
        from pipeline.video_gen import poll_until_complete
        with pytest.raises(RuntimeError, match="HeyGen render failed"):
            poll_until_complete("abc-123")


def test_poll_raises_timeout_when_deadline_exceeded():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"status": "processing"}}
    with patch("pipeline.video_gen.requests.get", return_value=mock_resp), \
         patch("pipeline.video_gen.time.sleep"), \
         patch("pipeline.video_gen.POLL_TIMEOUT", -1):
        from pipeline.video_gen import poll_until_complete
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
        from pipeline.video_gen import download_video
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
        from pipeline.video_gen import download_video
        download_video("https://example.com/video.mp4", dest)
    assert dest.exists()
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_video_gen.py -v
```

Expected: `ModuleNotFoundError` — `pipeline/video_gen.py` does not exist yet.

- [ ] **Step 3: Implement pipeline/video_gen.py**

```python
import logging
import os
import time
import uuid
from pathlib import Path

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

BASE_URL = "https://api.heygen.com"
POLL_INTERVAL = 10
POLL_TIMEOUT = 600


def _heygen_headers() -> dict:
    return {
        "X-Api-Key": os.environ["HEYGEN_API_KEY"],
        "Content-Type": "application/json",
    }


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code >= 500
    return False


def create_video(narration: str) -> str:
    payload = {
        "video_inputs": [
            {
                "character": {
                    "type": "avatar",
                    "avatar_id": os.environ["HEYGEN_AVATAR_ID"],
                    "avatar_style": "normal",
                },
                "voice": {
                    "type": "text",
                    "input_text": narration,
                    "voice_id": os.environ["HEYGEN_VOICE_ID"],
                },
            }
        ],
        "dimension": {"width": 1080, "height": 1920},
    }
    headers = _heygen_headers()
    headers["Idempotency-Key"] = str(uuid.uuid4())
    resp = requests.post(f"{BASE_URL}/v2/video/generate", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()["data"]["video_id"]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, exp_base=3, min=5, max=45),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
def _fetch_video_status(video_id: str) -> dict:
    resp = requests.get(f"{BASE_URL}/v3/videos/{video_id}", headers=_heygen_headers())
    resp.raise_for_status()
    return resp.json()["data"]


def poll_until_complete(video_id: str) -> str:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        data = _fetch_video_status(video_id)
        status = data["status"]
        logger.info("[%s] status=%s", video_id, status)

        if status == "completed":
            return data["video_url"]
        if status == "failed":
            code = data.get("failure_code", "unknown")
            msg = data.get("failure_message", "no message")
            logger.error("[%s] failed: code=%s message=%s", video_id, code, msg)
            raise RuntimeError(f"HeyGen render failed: {code} — {msg}")

        time.sleep(POLL_INTERVAL)

    raise TimeoutError(f"HeyGen render timed out after {POLL_TIMEOUT}s for video {video_id}")


def download_video(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)
    return dest
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_video_gen.py -v
```

Expected:
```
tests/test_video_gen.py::test_create_video_returns_video_id PASSED
tests/test_video_gen.py::test_create_video_posts_correct_dimensions PASSED
tests/test_video_gen.py::test_create_video_includes_idempotency_key PASSED
tests/test_video_gen.py::test_poll_returns_url_on_completed PASSED
tests/test_video_gen.py::test_poll_raises_runtime_error_on_failed PASSED
tests/test_video_gen.py::test_poll_raises_timeout_when_deadline_exceeded PASSED
tests/test_video_gen.py::test_download_video_writes_file_contents PASSED
tests/test_video_gen.py::test_download_video_creates_parent_dirs PASSED
8 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/video_gen.py tests/test_video_gen.py
git commit -m "feat: add video_gen module (HeyGen render + polling + download)"
```

---

## Task 4: youtube_upload.py

**Files:**
- Create: `tests/test_youtube_upload.py`
- Create: `pipeline/youtube_upload.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_youtube_upload.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_youtube_upload.py -v
```

Expected: `ModuleNotFoundError` — `pipeline/youtube_upload.py` does not exist yet.

- [ ] **Step 3: Implement pipeline/youtube_upload.py**

```python
import argparse
import json
import os
import sys
from pathlib import Path

import googleapiclient.discovery
import googleapiclient.http
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from tenacity import retry, stop_after_attempt, wait_exponential

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path(".youtube_token.json")
CHUNK_SIZE = 1024 * 1024


def _get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.environ["YOUTUBE_CLIENT_SECRETS_PATH"], SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, exp_base=3, min=5, max=45),
    reraise=True,
)
def upload_video(video_path: Path, metadata: dict, publish_at: str) -> str:
    creds = _get_credentials()
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
        },
    }
    media = googleapiclient.http.MediaFileUpload(
        str(video_path), mimetype="video/mp4", chunksize=CHUNK_SIZE, resumable=True
    )
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()

    return f"https://www.youtube.com/watch?v={response['id']}"


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Upload an approved video to YouTube")
    parser.add_argument("video_path", type=Path, help="Path to video in output/approved/")
    parser.add_argument("--publish-at", required=True, help="ISO 8601 publish timestamp")
    args = parser.parse_args()

    sidecar = args.video_path.with_suffix(".json")
    if not sidecar.exists():
        print(f"Error: sidecar metadata not found: {sidecar}", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(sidecar.read_text())
    url = upload_video(args.video_path, meta, args.publish_at)
    print(f"Uploaded: {url}")
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_youtube_upload.py -v
```

Expected:
```
tests/test_youtube_upload.py::test_upload_video_returns_youtube_url PASSED
tests/test_youtube_upload.py::test_upload_video_sets_correct_body PASSED
tests/test_youtube_upload.py::test_get_credentials_returns_valid_cached_token PASSED
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/youtube_upload.py tests/test_youtube_upload.py
git commit -m "feat: add youtube_upload module (OAuth2, resumable upload, retries)"
```

---

## Task 5: main.py

**Files:**
- Create: `tests/test_main.py`
- Create: `main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError` — `main.py` does not exist yet.

- [ ] **Step 3: Implement main.py**

```python
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from pipeline import script_gen, video_gen

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

PENDING_DIR = Path("output/pending_review")
APPROVED_DIR = Path("output/approved")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a kids' educational YouTube Short")
    parser.add_argument("topic", help="The educational topic for the video")
    args = parser.parse_args()

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Generating script for topic: %s", args.topic)
    script = script_gen.generate_script(args.topic)
    logger.info("Script generated. Title: %s", script["title"])

    logger.info("Submitting render job to HeyGen...")
    video_id = video_gen.create_video(script["narration"])
    logger.info("Render job created. video_id=%s", video_id)

    logger.info("Polling HeyGen for render completion (timeout: 10 min)...")
    download_url = video_gen.poll_until_complete(video_id)
    logger.info("Render complete. Downloading...")

    video_path = PENDING_DIR / f"{video_id}.mp4"
    video_gen.download_video(download_url, video_path)
    logger.info("Video saved to %s", video_path)

    sidecar = {
        "title": script["title"],
        "description": script["description"],
        "tags": script["tags"],
        "topic": args.topic,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar_path = PENDING_DIR / f"{video_id}.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2))
    logger.info("Metadata saved to %s", sidecar_path)

    print("\n" + "=" * 60)
    print("REVIEW REQUIRED — DO NOT UPLOAD YET")
    print("=" * 60)
    print(f"  Video:    {video_path}")
    print(f"  Metadata: {sidecar_path}")
    print()
    print("Steps:")
    print("  1. Watch the video in output/pending_review/")
    print("  2. If approved, run:")
    print(f"       python approve.py {video_id}.mp4")
    print("  3. Then upload to YouTube:")
    print(
        f"       python pipeline/youtube_upload.py output/approved/{video_id}.mp4"
        " --publish-at 'YYYY-MM-DDTHH:MM:SSZ'"
    )
    print("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        sys.exit(1)
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_main.py -v
```

Expected:
```
tests/test_main.py::test_main_calls_pipeline_in_order PASSED
tests/test_main.py::test_main_writes_sidecar_json PASSED
tests/test_main.py::test_main_creates_output_directories PASSED
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add main.py orchestrator CLI"
```

---

## Task 6: approve.py

**Files:**
- Create: `tests/test_approve.py`
- Create: `approve.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_approve.py`:

```python
import pytest
from pathlib import Path


@pytest.fixture
def output_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output" / "pending_review").mkdir(parents=True)
    (tmp_path / "output" / "approved").mkdir(parents=True)
    return tmp_path


def test_approve_moves_video_and_sidecar(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-123.mp4"
    jf = tmp_path / "output" / "pending_review" / "abc-123.json"
    mp4.write_bytes(b"fake video")
    jf.write_text('{"title": "test"}')

    import approve
    approve.approve("abc-123.mp4")

    assert not mp4.exists()
    assert not jf.exists()
    assert (tmp_path / "output" / "approved" / "abc-123.mp4").exists()
    assert (tmp_path / "output" / "approved" / "abc-123.json").exists()


def test_approve_accepts_full_path_prefix(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-456.mp4"
    jf = tmp_path / "output" / "pending_review" / "abc-456.json"
    mp4.write_bytes(b"fake")
    jf.write_text("{}")

    import approve
    approve.approve("output/pending_review/abc-456.mp4")

    assert (tmp_path / "output" / "approved" / "abc-456.mp4").exists()


def test_approve_raises_on_missing_video(output_dirs):
    import approve
    with pytest.raises(FileNotFoundError, match="Video not found"):
        approve.approve("nonexistent.mp4")


def test_approve_raises_on_missing_sidecar(output_dirs):
    tmp_path = output_dirs
    mp4 = tmp_path / "output" / "pending_review" / "abc-789.mp4"
    mp4.write_bytes(b"fake")

    import approve
    with pytest.raises(FileNotFoundError, match="Sidecar metadata not found"):
        approve.approve("abc-789.mp4")
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_approve.py -v
```

Expected: `ModuleNotFoundError` — `approve.py` does not exist yet.

- [ ] **Step 3: Implement approve.py**

```python
import argparse
import shutil
import sys
from pathlib import Path

PENDING_DIR = Path("output/pending_review")
APPROVED_DIR = Path("output/approved")


def approve(filename: str) -> None:
    name = Path(filename).name
    stem = Path(name).stem

    mp4_src = PENDING_DIR / name
    json_src = PENDING_DIR / f"{stem}.json"

    if not mp4_src.exists():
        raise FileNotFoundError(f"Video not found: {mp4_src}")
    if not json_src.exists():
        raise FileNotFoundError(f"Sidecar metadata not found: {json_src}")

    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(mp4_src), str(APPROVED_DIR / name))
    shutil.move(str(json_src), str(APPROVED_DIR / f"{stem}.json"))

    print(f"Approved: {APPROVED_DIR / name}")
    print(f"Metadata: {APPROVED_DIR / f'{stem}.json'}")
    print()
    print("Ready to upload. Run:")
    print(
        f"  python pipeline/youtube_upload.py output/approved/{name}"
        " --publish-at 'YYYY-MM-DDTHH:MM:SSZ'"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Move a reviewed video from pending_review to approved"
    )
    parser.add_argument("filename", help="Filename in output/pending_review/ (e.g. abc123.mp4)")
    args = parser.parse_args()

    try:
        approve(args.filename)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_approve.py -v
```

Expected:
```
tests/test_approve.py::test_approve_moves_video_and_sidecar PASSED
tests/test_approve.py::test_approve_accepts_full_path_prefix PASSED
tests/test_approve.py::test_approve_raises_on_missing_video PASSED
tests/test_approve.py::test_approve_raises_on_missing_sidecar PASSED
4 passed
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all 19 tests pass.

- [ ] **Step 6: Commit**

```bash
git add approve.py tests/test_approve.py
git commit -m "feat: add approve.py file-mover helper"
```

---

## Task 7: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

````markdown
# YouTube Shorts Kids' Education Pipeline

Generates kids' educational YouTube Shorts end-to-end: Claude writes the
script → HeyGen renders an avatar video → you review it → pipeline uploads
to YouTube on a scheduled private publish date.

## Prerequisites

- Python 3.10+
- Anthropic API key
- HeyGen API key with an avatar and voice configured
- Google Cloud project with YouTube Data API v3 enabled and an OAuth2
  desktop client credentials JSON file

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in secrets
cp .env.example .env
# Edit .env with your actual keys and paths
```

## Usage

### Step 1 — Generate and render

```bash
python main.py "why is the sky blue"
```

Calls Claude to write a 45–60 second narration, submits a render job to
HeyGen (1080×1920, 9:16), polls until the video is ready (up to 10 minutes),
and downloads it to `output/pending_review/`.

### Step 2 — Review

Watch the video in `output/pending_review/`. When satisfied:

```bash
python approve.py <video_id>.mp4
```

Moves the `.mp4` and its `.json` metadata sidecar to `output/approved/`.

### Step 3 — Upload to YouTube

```bash
python pipeline/youtube_upload.py output/approved/<video_id>.mp4 \
  --publish-at "2026-07-01T18:00:00Z"
```

On first run, a browser window opens for Google OAuth2 consent. The refresh
token is cached to `.youtube_token.json` for subsequent runs.

The video is uploaded as **private** and scheduled to go public at the
timestamp you supply. Check YouTube Studio to confirm.

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `HEYGEN_API_KEY` | HeyGen API key |
| `HEYGEN_AVATAR_ID` | ID of the HeyGen avatar to use |
| `HEYGEN_VOICE_ID` | ID of the HeyGen voice to use |
| `YOUTUBE_CLIENT_SECRETS_PATH` | Path to Google OAuth2 client secrets JSON |

## Running Tests

```bash
pytest tests/ -v
```
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```
