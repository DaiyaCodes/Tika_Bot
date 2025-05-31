import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # Upload this securely

FOLDER_ID = '1eUge3ObEUS_9fPfAItZlfCiFQFgh6H4j'  # Create a folder on Google Drive and get its ID

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)


def upload_json(file_path: str, file_name: str):
    """Uploads a JSON file to Google Drive (overwrite if exists)."""
    # Check if file already exists
    existing_files = drive_service.files().list(
        q=f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()

    media = MediaFileUpload(file_path, mimetype='application/json')

    if existing_files['files']:
        file_id = existing_files['files'][0]['id']
        drive_service.files().update(fileId=file_id, media_body=media).execute()
    else:
        drive_service.files().create(
            body={
                'name': file_name,
                'parents': [FOLDER_ID],
                'mimeType': 'application/json'
            },
            media_body=media
        ).execute()


def download_json(file_name: str, save_to: str):
    """Downloads a JSON file from Google Drive to a local path."""
    results = drive_service.files().list(
        q=f"name='{file_name}' and '{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()

    files = results.get('files', [])
    if not files:
        return False

    file_id = files[0]['id']
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(save_to, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return True
