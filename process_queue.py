import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_exponential

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

DRIVE_QUEUE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_QUEUE_FOLDER_ID")
DRIVE_PROCESSING_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_PROCESSING_FOLDER_ID")
DRIVE_PUBLISHED_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_PUBLISHED_FOLDER_ID")
DRIVE_FAILED_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FAILED_FOLDER_ID")

YOUTUBE_SCOPES = [
      "https://www.googleapis.com/auth/youtube",
      "https://www.googleapis.com/auth/youtube.upload",
]

def get_service_account_credentials():
      if not SERVICE_ACCOUNT_JSON:
                raise RuntimeError("SERVICE_ACCOUNT_JSON secret not found")
            creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    return ServiceAccountCredentials.from_service_account_info(creds_dict)

def get_youtube_credentials():
      if not YOUTUBE_TOKEN_JSON:
                raise RuntimeError("YOUTUBE_TOKEN_JSON secret not found")
            token_info = json.loads(YOUTUBE_TOKEN_JSON)
    creds = Credentials.from_authorized_user_info(token_info, scopes=YOUTUBE_SCOPES)
    if creds.expired and creds.refresh_token:
              creds.refresh(Request())
          return creds

def get_sheet():
      sa_creds = get_service_account_credentials()
    gc = gspread.authorize(sa_creds)
    worksheet = gc.open_by_key(SHEET_ID).sheet1
    return worksheet

def download_video_from_drive(file_id, output_path):
      sa_creds = get_service_account_credentials()
    drive_service = build("drive", "v3", credentials=sa_creds)
    request = drive_service.files().get_media(fileId=file_id)
    with open(output_path, "wb") as f:
              downloader = MediaIoBaseDownload(f, request)
              done = False
              while not done:
                            status, done = downloader.next_chunk()
                    print(f"Downloaded: {output_path}")

def upload_to_youtube(video_path, row_data):
      yt_creds = get_youtube_credentials()
    youtube = build("youtube", "v3", credentials=yt_creds)

    title = row_data.get("youtube_title", "Untitled")
    description = row_data.get("youtube_description", "")
    tags = row_data.get("youtube_tags", "").split(",") if row_data.get("youtube_tags") else []
    category_id = row_data.get("youtube_category_id", "22")
    privacy = row_data.get("youtube_privacy", "private")

    body = {
              "snippet": {
                            "title": title,
                            "description": description,
                            "tags": tags,
                            "categoryId": category_id,
              },
              "status": {
                            "privacyStatus": privacy,
                            "selfDeclaredMadeForKids": False,
              },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
              part="snippet,status",
              body=body,
              media_body=media,
    )

    response = None
    while response is None:
              status, response = request.next_chunk()
        if status:
                      progress = int(status.progress() * 100)
                      print(f"YouTube upload progress: {progress}%")

    video_id = response["id"]
    print(f"YouTube upload complete. Video ID: {video_id}")
    return video_id

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def process_row(row_number, row_data):
      try:
                sheet = get_sheet()

        row_id = row_data.get("id")
        print(f"\n=== Processing row {row_number} (ID: {row_id}) ===")

        drive_file_id = row_data.get("drive_file_id")
        if not drive_file_id:
                      raise ValueError("drive_file_id not found in row")

        video_path = Path(f"/tmp/video_{row_id}.mp4")
        download_video_from_drive(drive_file_id, str(video_path))

        if row_data.get("youtube_enabled"):
                      video_id = upload_to_youtube(str(video_path), row_data)
                      row_data["youtube_video_id"] = video_id
                      row_data["youtube_status"] = "PUBLISHED"
else:
            row_data["youtube_status"] = "SKIPPED"

        row_data["status"] = "PUBLISHED"
                  row_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        col_map = {
                      "id": 1, "drive_file_id": 15, "publish_at": 16, "timezone": 17,
                      "youtube_category_id": 18, "youtube_privacy": 19, "instagram_share_to_feed": 20,
                      "tiktok_privacy": 21, "tiktok_allow_comments": 22, "tiktok_allow_duet": 23,
                      "tiktok_allow_stitch": 24, "youtube_video_id": 25, "instagram_media_id": 26,
                      "tiktok_publish_id": 27, "attempts": 28, "last_error": 29, "locked_at": 30,
                      "created_at": 31, "updated_at": 32,
                      "youtube_status": 11, "instagram_status": 12, "tiktok_status": 13,
        }

        for key, col in col_map.items():
                      if key in row_data and row_data[key] is not None:
                                        sheet.update_cell(row_number, col, row_data[key])

                  print(f"Row {row_number} updated successfully")
        video_path.unlink(missing_ok=True)

except Exception as e:
        print(f"Error processing row {row_number}: {e}")
        row_data["last_error"] = str(e)
        row_data["status"] = "FAILED"
        row_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        raise

def main():
      sheet = get_sheet()
    all_rows = sheet.get_all_records()

    now = datetime.now(timezone.utc)

    pending_rows = []
    for idx, row in enumerate(all_rows, start=2):
              if row.get("status") == "PENDING":
                            publish_at_str = row.get("publish_at")
                            if publish_at_str:
                                              try:
                                                                    publish_at = datetime.fromisoformat(publish_at_str.replace("Z", "+00:00"))
                                                                    if publish_at <= now:
                                                                                              pending_rows.append((idx, row))
                                              except ValueError:
                                                                    pass

                                  if not pending_rows:
                                            print("No pending rows to process")
                                            return

                    print(f"Found {len(pending_rows)} rows to process")

    for row_number, row_data in pending_rows:
              try:
                            process_row(row_number, row_data)
except Exception as e:
            print(f"Failed to process row {row_number}: {e}")

if __name__ == "__main__":
      main()
