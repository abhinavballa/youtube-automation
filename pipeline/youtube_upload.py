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

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = Path(__file__).parent.parent / ".youtube_token.json"
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
        part="snippet,status",
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
