import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

VIDEO_PATH = "test_video.mp4"


def main():
    secret = os.environ.get("YOUTUBE_TOKEN_JSON")

    if not secret:
        raise RuntimeError(
            "O secret YOUTUBE_TOKEN_JSON nao foi encontrado."
        )

    if not os.path.exists(VIDEO_PATH):
        raise RuntimeError(
            f"Ficheiro de video de teste nao encontrado: {VIDEO_PATH}"
        )

    token_info = json.loads(secret)

    credentials = Credentials.from_authorized_user_info(
        token_info,
        scopes=SCOPES,
    )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
    )

    body = {
        "snippet": {
            "title": "Teste automatico - Auto Video Publisher",
            "description": "Video de teste enviado automaticamente pelo Auto Video Publisher. Pode ser apagado.",
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(VIDEO_PATH, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]

    print("Upload de teste concluido com sucesso.")
    print("ID do video:", video_id)
    print("Link (privado): https://youtu.be/" + video_id)


if __name__ == "__main__":
    main()
