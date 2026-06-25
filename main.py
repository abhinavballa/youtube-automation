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
