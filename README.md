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
