import os
import time
from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _get_drive_service():
    """
    Build a Drive client.
    Priority:
      1. OAuth client secrets (env GOOGLE_CLIENT_SECRETS). Token cached in
         GOOGLE_TOKEN_FILE or ~/.cache/fly_tcoma_drive_token.json
      2. Service account JSON via GDRIVE_SERVICE_ACCOUNT_FILE or GOOGLE_APPLICATION_CREDENTIALS.
    """
    client_secrets = os.getenv("GOOGLE_CLIENT_SECRETS")
    if client_secrets:
        token_path = os.getenv("GOOGLE_TOKEN_FILE") or str(Path.home() / ".cache" / "fly_tcoma_drive_token.json")
        token_file = Path(token_path)
        creds = None
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(request=None)  # google-auth handles refresh internally
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
                creds = flow.run_local_server(port=0)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json())
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    cred_path = os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        raise FileNotFoundError(
            "Set GOOGLE_CLIENT_SECRETS for OAuth, or GDRIVE_SERVICE_ACCOUNT_FILE/GOOGLE_APPLICATION_CREDENTIALS for a service account."
        )
    creds = service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload_to_drive(file_path: str, folder_id: Optional[str] = None, drive_id: Optional[str] = None, max_retries: int = 3) -> str:
    """
    Upload a local file to Google Drive.
    Args:
        file_path: local path to upload.
        folder_id: optional Drive folder ID to place the file.
        drive_id: optional Shared Drive ID (recommended to avoid SA quota issues).
    Returns:
        The uploaded file ID.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    service = _get_drive_service()
    metadata = {"name": file_path.name}
    if folder_id:
        metadata["parents"] = [folder_id]
    # If using Shared Drives, specify driveId and supportsAllDrives.
    extra_kwargs = {}
    if drive_id:
        extra_kwargs["supportsAllDrives"] = True
        extra_kwargs["includeItemsFromAllDrives"] = True

    media = MediaFileUpload(str(file_path), resumable=True)
    backoff = 1.0
    for attempt in range(max_retries):
        try:
            uploaded = (
                service.files()
                .create(body=metadata, media_body=media, fields="id", **extra_kwargs)
                .execute()
            )
            return uploaded.get("id")
        except HttpError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff)
            backoff *= 2
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff)
            backoff *= 2
