import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    secret = os.environ.get("YOUTUBE_TOKEN_JSON")

    if not secret:
        raise RuntimeError(
            "O secret YOUTUBE_TOKEN_JSON não foi encontrado."
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

    response = youtube.channels().list(
        part="snippet",
        mine=True,
    ).execute()

    channels = response.get("items", [])

    if not channels:
        raise RuntimeError(
            "A ligação funcionou, mas nenhum canal do YouTube foi encontrado."
        )

    channel_name = channels[0]["snippet"]["title"]

    print("✅ Ligação ao YouTube realizada com sucesso.")
    print("✅ Canal encontrado:", channel_name)


if __name__ == "__main__":
    main()
