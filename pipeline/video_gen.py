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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, exp_base=3, min=5, max=45),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
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
    tmp = dest.with_suffix(".tmp")
    try:
        with requests.get(url, stream=True) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    fh.write(chunk)
        tmp.rename(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return dest
