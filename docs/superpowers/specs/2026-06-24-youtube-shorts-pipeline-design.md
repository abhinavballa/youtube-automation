# YouTube Shorts Kids' Education Pipeline — Design Spec
Date: 2026-06-24

## Overview

A Python automation pipeline that generates short kids' educational videos and
publishes them to YouTube Shorts. Triggered manually via CLI (scheduled by the
user via cron). Covers script generation, HeyGen avatar video rendering, a
mandatory human review checkpoint, and YouTube upload with scheduled publish.

---

## Project Structure

```
youtube-automation/
├── pipeline/
│   ├── __init__.py
│   ├── script_gen.py       # Claude API → narration text, title, tags
│   ├── video_gen.py        # HeyGen API → render + poll + download
│   └── youtube_upload.py   # YouTube Data API v3 OAuth2 upload
├── output/
│   ├── pending_review/     # video.mp4 + video.json land here (gitignored)
│   └── approved/           # approved videos wait here for upload (gitignored)
├── docs/
│   └── superpowers/specs/
├── main.py                 # CLI: python main.py "topic"  → runs steps 1–2
├── approve.py              # CLI: python approve.py <filename>  → moves to approved/
├── .env.example
├── requirements.txt
└── README.md
```

- `output/` subdirectories are created at runtime if missing.
- Both `output/` subdirs are `.gitignore`d (video files are large and private).
- `pipeline/` modules are pure functions — no global state — for testability.

---

## Environment Variables

All secrets read via `python-dotenv` from a `.env` file. No value is ever
hardcoded.

| Variable                      | Purpose                                              |
|-------------------------------|------------------------------------------------------|
| `ANTHROPIC_API_KEY`           | Claude API authentication                            |
| `HEYGEN_API_KEY`              | HeyGen API authentication                            |
| `HEYGEN_AVATAR_ID`            | HeyGen avatar to use for video rendering             |
| `HEYGEN_VOICE_ID`             | HeyGen voice to use for narration                    |
| `YOUTUBE_CLIENT_SECRETS_PATH` | Path to Google OAuth2 `client_secrets.json`          |

---

## Data Flow

```
main.py "topic"
    │
    ▼
script_gen.generate_script(topic)
  Model: claude-haiku-4-5
  Returns: {narration, title, description, tags}
    │
    ▼
video_gen.create_video(narration)
  POST /v2/video/generate
  Header: Idempotency-Key: <uuid4>
  Returns: video_id
    │
    ▼
video_gen.poll_until_complete(video_id)
  GET /v3/videos/{video_id} every 10s
  Timeout: 10 minutes (60 polls)
  On "failed": log failure_code + failure_message, raise RuntimeError
  Returns: download_url
    │
    ▼
video_gen.download_video(download_url, dest_path)
  Streaming download → output/pending_review/<video_id>.mp4
  Sidecar  →          output/pending_review/<video_id>.json
    │
    ▼  [PIPELINE STOPS — human reviews output/pending_review/]

approve.py <video_id>.mp4
  Moves <video_id>.mp4 + <video_id>.json → output/approved/
    │
    ▼
youtube_upload.py output/approved/<video_id>.mp4 --publish-at "2026-01-15T18:00:00Z"
  Reads sidecar JSON for title/description/tags
  OAuth2 flow (client_secrets.json → cached .youtube_token.json)
  Resumable upload via googleapiclient
  privacyStatus = "private", publishAt = --publish-at arg
  Prints YouTube video URL on success
```

---

## Sidecar JSON Schema

Written alongside each video in `output/pending_review/` and `output/approved/`:

```json
{
  "title": "Why Do Stars Twinkle?",
  "description": "Learn why stars twinkle at night in this fun video for kids!",
  "tags": ["kids", "science", "stars", "space", "education"],
  "topic": "why do stars twinkle",
  "generated_at": "2026-06-24T10:30:00Z"
}
```

---

## Module Specifications

### `pipeline/script_gen.py`

**Function:** `generate_script(topic: str) -> dict`

- Calls Claude `claude-haiku-4-5` via `anthropic` Python SDK.
- System prompt instructs the model to write a 45–60 second kids' narration
  for a single on-screen presenter/avatar to read aloud, and return a JSON
  object with keys: `narration` (str), `title` (str), `description` (str),
  `tags` (list of 3–5 str).
- Parses the JSON from the response content.
- Raises `ValueError` if the response cannot be parsed as valid JSON with the
  expected keys.
- Returns the parsed dict.

### `pipeline/video_gen.py`

**Constants (from env):** `HEYGEN_API_KEY`, `HEYGEN_AVATAR_ID`, `HEYGEN_VOICE_ID`  
**Base URL:** `https://api.heygen.com`  
**Auth header:** `X-Api-Key: <HEYGEN_API_KEY>`

**Function:** `create_video(narration: str) -> str`

- POST `/v2/video/generate` with:
  - `avatar_id`, `voice_id` from env vars
  - `script.type = "text"`, `script.input = narration`
  - `dimension = {"width": 1080, "height": 1920}` (9:16 for Shorts)
  - Header `Idempotency-Key: <uuid4>` (generated fresh per call)
- Returns `video_id` from response.

**Function:** `poll_until_complete(video_id: str) -> str`

- Polls `GET /v3/videos/{video_id}` every 10 seconds.
- On `"completed"`: returns download URL from response.
- On `"failed"`: logs `failure_code` and `failure_message`, raises `RuntimeError`.
- On timeout (10 minutes / 60 polls): raises `TimeoutError`.
- The GET call itself is wrapped with `tenacity.retry`:
  - 3 attempts, waits: 5s → 15s → 45s (exponential).
  - Retries on network/5xx errors only, not on `"failed"` status.

**Function:** `download_video(url: str, dest: Path) -> Path`

- Downloads the video via `requests` with `stream=True` to avoid loading the
  full file into memory.
- Writes to `dest` (caller supplies the path).
- Returns `dest`.

### `pipeline/youtube_upload.py`

**Function:** `upload_video(video_path: Path, metadata: dict, publish_at: str) -> str`

- Loads OAuth2 credentials from `YOUTUBE_CLIENT_SECRETS_PATH`.
- Caches refresh token to `.youtube_token.json` (local, gitignored).
- If cached token is expired, refreshes automatically; if missing, runs
  browser-based auth flow once.
- Builds upload request via `googleapiclient.discovery` (YouTube Data API v3).
- Sets:
  - `snippet.title` = `metadata["title"]`
  - `snippet.description` = `metadata["description"]`
  - `snippet.tags` = `metadata["tags"]`
  - `snippet.categoryId` = `"27"` (Education)
  - `status.privacyStatus` = `"private"`
  - `status.publishAt` = `publish_at` (ISO 8601 string from CLI)
- Uses resumable upload (`MediaFileUpload` with `resumable=True`).
- Wrapped with `tenacity.retry`: 3 attempts, 5s → 15s → 45s.
- Returns the YouTube video URL on success.

### `main.py`

```
python main.py "why do stars twinkle"
```

- Loads `.env` via `python-dotenv`.
- Creates `output/pending_review/` and `output/approved/` if missing.
- Logs each step to stdout with ISO timestamps.
- Calls `script_gen.generate_script()` → `video_gen.create_video()` →
  `video_gen.poll_until_complete()` → `video_gen.download_video()`.
- Writes the sidecar JSON after successful download.
- Prints a prominent message telling the user to review the file in
  `output/pending_review/` and run `approve.py` when ready.
- Exits non-zero on any unhandled exception.

### `approve.py`

```
python approve.py <filename>
```

- Accepts a filename (with or without path prefix).
- Moves `output/pending_review/<filename>` and the corresponding `.json`
  sidecar to `output/approved/`.
- Errors clearly if either file is not found.

---

## Retry Strategy

Using `tenacity` library throughout.

| Call site                        | Attempts | Waits          |
|----------------------------------|----------|----------------|
| HeyGen GET poll (network/5xx)    | 3        | 5s, 15s, 45s   |
| YouTube upload                   | 3        | 5s, 15s, 45s   |

HeyGen `"failed"` status is **not** retried — it is a terminal state from
HeyGen's side, not a transient error.

---

## Dependencies (`requirements.txt`)

```
anthropic
requests
tenacity
python-dotenv
google-api-python-client
google-auth-oauthlib
google-auth-httplib2
```

---

## Security

- `.env`, `.youtube_token.json`, `client_secrets.json`, and `output/` are
  all `.gitignore`d.
- No secret is logged to stdout. Only topic, video IDs, and status messages
  are printed.

---

## Out of Scope

- Scheduling (user handles via cron).
- Batch processing (one topic per `main.py` invocation).
- Video thumbnail generation.
- Analytics or reporting.
