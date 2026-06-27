# Content-Aware Avatar & Voice Casting — Design Spec

## Goal

Remove the hardcoded `HEYGEN_AVATAR_ID` and `HEYGEN_VOICE_ID` from configuration.
Instead, automatically select an avatar and voice that suit each video's content by
fetching the catalog available to the user's HeyGen account and letting Claude choose
the best kid-appropriate fit per video.

## Motivation

Today `pipeline/video_gen.create_video` reads `HEYGEN_AVATAR_ID` and `HEYGEN_VOICE_ID`
from the environment. This forces the user to look up and pin specific IDs, and the same
presenter/voice is used for every video regardless of topic. The user wants:

1. To not manage avatar/voice IDs in `.env`.
2. The avatar and voice to vary per video and suit the content.

## Key Constraint

HeyGen `avatar_id` and `voice_id` values are not free-form. Each references an avatar or
voice that exists in the user's HeyGen account or HeyGen's public library. Selection must
therefore be made **from the catalog the account actually has access to** — Claude cannot
invent IDs. The catalog is retrieved via:

- `GET /v2/avatars` — returns avatars (and talking photos; we use avatars only)
- `GET /v2/voices` — returns voices

## Architecture

### New module: `pipeline/casting.py`

A focused module whose single responsibility is: given a generated script, return a
fitting `{avatar_id, voice_id}`.

**Functions:**

- `list_avatars() -> list[dict]`
  - `GET {BASE_URL}/v2/avatars` with HeyGen auth headers.
  - Returns a normalized list of `{"avatar_id": str, "name": str, "gender": str}`.
  - Uses the same retry policy as the rest of `video_gen` (retry on connection/timeout
    and 5xx).

- `list_voices() -> list[dict]`
  - `GET {BASE_URL}/v2/voices` with HeyGen auth headers.
  - Returns a normalized list of `{"voice_id": str, "name": str, "language": str, "gender": str}`.
  - Same retry policy.

- `select_cast(script: dict) -> dict`
  - Fetches both catalogs.
  - Filters voices to English (e.g. `language` contains "English") to keep the choice
    relevant and the Claude token cost down. Avatars are not language-specific, so the
    full avatar list is used.
  - Sends a trimmed catalog (only the normalized fields above) plus the script's
    `title`, `narration`, and `tags` to Claude with a "casting director for a kids'
    educational channel" system prompt.
  - Claude returns JSON `{"avatar_id": ..., "voice_id": ...}`.
  - **Validation / hallucination guard:** the returned `avatar_id` and `voice_id` are
    checked for membership in the fetched catalogs. If either is invalid, or the catalog
    came back empty for that category, fall back to the first available option in that
    category. If a category has zero options at all, raise a clear `RuntimeError`.
  - Returns `{"avatar_id": str, "voice_id": str}`.

Shared HeyGen constants/headers (`BASE_URL`, `_heygen_headers`, `_should_retry`) currently
live in `pipeline/video_gen.py`. `casting.py` will import and reuse them rather than
duplicating, keeping a single source of truth for HeyGen auth and retry behavior.

The Claude client construction mirrors `pipeline/script_gen.py` (reads `ANTHROPIC_API_KEY`,
uses `claude-haiku-4-5`).

### Changed: `pipeline/video_gen.create_video`

Signature changes from:

```python
def create_video(narration: str) -> str:
```

to:

```python
def create_video(narration: str, avatar_id: str, voice_id: str) -> str:
```

The `os.environ["HEYGEN_AVATAR_ID"]` and `os.environ["HEYGEN_VOICE_ID"]` reads are removed;
the IDs come from the explicit arguments. `HEYGEN_API_KEY` is still read via
`_heygen_headers`. All other behavior (payload shape, dimensions, idempotency key, retry)
is unchanged.

### Changed: `main.py`

```python
script   = script_gen.generate_script(topic)
cast     = casting.select_cast(script)
video_id = video_gen.create_video(script["narration"], cast["avatar_id"], cast["voice_id"])
```

A log line records the chosen avatar/voice for traceability.

### Config cleanup

- Remove `HEYGEN_AVATAR_ID` and `HEYGEN_VOICE_ID` from `.env.example`.
- Remove those two rows from the README environment-variable table.
- `HEYGEN_API_KEY` and `ANTHROPIC_API_KEY` remain required.

## Data Flow

```
topic
  → script_gen.generate_script(topic) → {narration, title, description, tags}
  → casting.select_cast(script):
        list_avatars(), list_voices()  (HeyGen GETs)
        → filter voices to English
        → Claude chooses {avatar_id, voice_id}
        → validate against catalog (fallback on miss)
  → video_gen.create_video(narration, avatar_id, voice_id) → video_id
  → poll / download / sidecar  (unchanged)
```

## Error Handling

- Catalog GETs use the existing connection/timeout/5xx retry policy.
- Claude returning non-JSON or missing keys → `ValueError` (same style as `script_gen`).
- Claude returning an ID not in the catalog → fall back to first available option in that
  category (logged at WARNING).
- A category with zero available options → `RuntimeError` with a clear message (the account
  has no usable avatars/voices).

## Testing

New `tests/test_casting.py`:
- `list_avatars` / `list_voices` normalize the HeyGen response shape (mock `requests.get`).
- `select_cast` returns the IDs Claude picks when they are valid (mock catalogs + mock
  Claude).
- `select_cast` filters non-English voices out of what Claude sees.
- `select_cast` falls back to the first available option when Claude returns an invalid ID.
- `select_cast` raises `RuntimeError` when a catalog is empty.

Updated tests:
- `tests/test_video_gen.py` — `create_video` tests pass `avatar_id`/`voice_id` as arguments
  instead of relying on env vars.
- `tests/test_main.py` — patches `main.casting.select_cast` and asserts its result is
  threaded into `create_video`.

## Out of Scope (YAGNI)

- Caching the catalog between runs (one extra pair of GETs per video is acceptable).
- Manual pin/override via env vars (can be added later if desired; the user explicitly
  wants no IDs in `.env`).
- Non-English voice support / multi-language channels.
- Talking-photo avatars.
