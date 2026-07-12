import json
import os
from datetime import datetime, timezone
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN_JSON")

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

def main():
          print("Starting queue processor...")
    sheet = get_sheet()
    all_rows = sheet.get_all_records()

    now = datetime.now(timezone.utc)
    print(f"Current time: {now.isoformat()}")

    pending_rows = []
    for idx, row in enumerate(all_rows, start=2):
                  status = row.get("status", "").strip().upper()
        if status == "PENDING":
                          publish_at_str = row.get("publish_at", "").strip()
                          if publish_at_str:
                                                try:
                                                                          publish_at = datetime.fromisoformat(publish_at_str.replace("Z", "+00:00"))
                                                                          if publish_at <= now:
                                                                                                        pending_rows.append((idx, row))
                                                                                                        print(f"Found pending row {idx}: {row.get('id')}")
                                                      except ValueError as e:
                                                    print(f"Could not parse publish_at for row {idx}: {publish_at_str} ({e})")

                  if not pending_rows:
                                print("No pending rows to process")
                                return

    print(f"Found {len(pending_rows)} rows ready to process")

    for row_number, row_data in pending_rows:
                  try:
                                    row_id = row_data.get("id")
                                    print(f"\n=== Processing row {row_number} (ID: {row_id}) ===")

            drive_file_id = row_data.get("drive_file_id", "").strip()
            if not drive_file_id:
                                  raise ValueError("drive_file_id is empty or missing")

            youtube_enabled = str(row_data.get("youtube_enabled", "FALSE")).upper() == "TRUE"
            if not youtube_enabled:
                                  print(f"YouTube disabled for row {row_id}, skipping")
                                  sheet.update_cell(row_number, sheet.find("status").col, "SKIPPED")
                                  continue

            video_path = Path(f"/tmp/video_{row_id}_{datetime.now().timestamp()}.mp4")
            download_video_from_drive(drive_file_id, str(video_path))

            video_id = upload_to_youtube(str(video_path), row_data)

            sheet.update_cell(row_number, sheet.find("youtube_video_id").col, video_id)
            sheet.update_cell(row_number, sheet.find("youtube_status").col, "PUBLISHED")
            sheet.update_cell(row_number, sheet.find("status").col, "PUBLISHED")
            sheet.update_cell(row_number, sheet.find("updated_at").col, datetime.now(timezone.utc).isoformat())

            print(f"Row {row_number} processed successfully")
            video_path.unlink(missing_ok=True)

except Exception as e:
            print(f"Error processing row {row_number}: {e}")
            try:
                                  sheet.update_cell(row_number, sheet.find("status").col, "FAILED")
                                  sheet.update_cell(row_number, sheet.find("last_error").col, str(e)[:100])
                                  sheet.update_cell(row_number, sheet.find("updated_at").col, datetime.now(timezone.utc).isoformat())
except Exception as update_error:
                print(f"Could not update sheet for row {row_number}: {update_error}")

if __name__ == "__main__":
          main()
