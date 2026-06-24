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
