import json
import os

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def main():
    secret = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not secret:
        raise RuntimeError(
            "O secret GOOGLE_SERVICE_ACCOUNT_JSON não foi encontrado."
        )

    account_info = json.loads(secret)

    credentials = Credentials.from_service_account_info(
        account_info,
        scopes=SCOPES,
    )

    # Testar a planilha
    client = gspread.authorize(credentials)
    spreadsheet = client.open("AGENDA_POSTAGENS")
    worksheet = spreadsheet.sheet1

    print("✅ Planilha encontrada:", spreadsheet.title)
    print("✅ Colunas encontradas:", worksheet.row_values(1))

    # Testar o Google Drive
    drive = build("drive", "v3", credentials=credentials)

    result = drive.files().list(
        q="trashed = false",
        pageSize=100,
        fields="files(id, name, mimeType)",
    ).execute()

    files = result.get("files", [])

    print("✅ Ficheiros e pastas acessíveis ao robô:")

    for file in files:
        print("-", file["name"], "|", file["mimeType"])


if __name__ == "__main__":
    main()
