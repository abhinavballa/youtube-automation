import json
import logging
import os

import anthropic
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from pipeline.video_gen import BASE_URL, _heygen_headers, _should_retry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a casting director for a kids' educational YouTube Shorts channel.
Given the script and available avatars/voices, choose the avatar and voice that best suit the content and are appropriate for children aged 5-10.

Return ONLY a JSON object with these keys:
- "avatar_id": the ID of the chosen avatar (string)
- "voice_id": the ID of the chosen voice (string)

Return only the JSON object. No markdown, no code fences, no other text.\
"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, exp_base=3, min=5, max=45),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
def list_avatars() -> list[dict]:
    """Fetch and normalize avatars from HeyGen API."""
    resp = requests.get(f"{BASE_URL}/v2/avatars", headers=_heygen_headers())
    resp.raise_for_status()
    body = resp.json()
    if "data" not in body or "avatars" not in body["data"]:
        raise RuntimeError(f"Unexpected HeyGen /v2/avatars response: {body}")
    avatars_data = body["data"]["avatars"]
    return [
        {
            "avatar_id": a["avatar_id"],
            "name": a["avatar_name"],
            "gender": a.get("gender", ""),
        }
        for a in avatars_data
    ]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, exp_base=3, min=5, max=45),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
def list_voices() -> list[dict]:
    """Fetch and normalize voices from HeyGen API."""
    resp = requests.get(f"{BASE_URL}/v2/voices", headers=_heygen_headers())
    resp.raise_for_status()
    body = resp.json()
    if "data" not in body or "voices" not in body["data"]:
        raise RuntimeError(f"Unexpected HeyGen /v2/voices response: {body}")
    voices_data = body["data"]["voices"]
    return [
        {
            "voice_id": v["voice_id"],
            "name": v["name"],
            "language": v["language"],
            "gender": v.get("gender", ""),
        }
        for v in voices_data
    ]


def select_cast(script: dict) -> dict:
    """
    Use Claude to select the best avatar and voice for the given script.

    Args:
        script: dict with keys like "title", "narration", "tags", "description"

    Returns:
        dict with "avatar_id" and "voice_id"

    Raises:
        RuntimeError: if no avatars or no English voices are available
        ValueError: if Claude response is not valid JSON
    """
    avatars = list_avatars()
    voices = list_voices()

    if not avatars:
        raise RuntimeError("No avatars available in HeyGen account")

    # Filter to English voices only
    english_voices = [v for v in voices if "english" in v["language"].lower()]
    if not english_voices:
        raise RuntimeError("No English voices available in HeyGen account")

    # Build Claude input with filtered catalogs
    user_content = f"""\
Script Title: {script.get("title", "")}
Narration: {script.get("narration", "")}
Tags: {script.get("tags", [])}
Description: {script.get("description", "")}

Available Avatars:
{json.dumps(avatars)}

Available Voices (English only):
{json.dumps(english_voices)}

Please select the best avatar and voice for this script.\
"""

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = message.content[0].text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Casting response is not valid JSON: {exc}\nResponse: {text}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Casting response is not a JSON object: {text}")

    # Validate IDs and fall back if needed
    valid_avatar_ids = {a["avatar_id"] for a in avatars}
    valid_voice_ids = {v["voice_id"] for v in english_voices}

    avatar_id = data.get("avatar_id")
    voice_id = data.get("voice_id")

    if avatar_id not in valid_avatar_ids:
        logger.warning(f"Claude selected invalid avatar_id: {avatar_id}. Falling back to {avatars[0]['avatar_id']}")
        avatar_id = avatars[0]["avatar_id"]

    if voice_id not in valid_voice_ids:
        logger.warning(f"Claude selected invalid voice_id: {voice_id}. Falling back to {english_voices[0]['voice_id']}")
        voice_id = english_voices[0]["voice_id"]

    return {"avatar_id": avatar_id, "voice_id": voice_id}
