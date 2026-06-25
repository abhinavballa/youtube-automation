import argparse
import shutil
import sys
from pathlib import Path

PENDING_DIR = Path("output/pending_review")
APPROVED_DIR = Path("output/approved")


def approve(filename: str) -> None:
    name = Path(filename).name
    stem = Path(filename).stem

    mp4_src = PENDING_DIR / name
    json_src = PENDING_DIR / f"{stem}.json"

    if not mp4_src.exists():
        raise FileNotFoundError(f"Video not found: {mp4_src}")
    if not json_src.exists():
        raise FileNotFoundError(f"Sidecar metadata not found: {json_src}")

    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(mp4_src, APPROVED_DIR / name)
    shutil.move(json_src, APPROVED_DIR / f"{stem}.json")

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
