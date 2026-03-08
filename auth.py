"""
Shared Google OAuth credential loading for Forms and Classroom APIs.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_REFRESH_RETRIES = 3
_REFRESH_RETRY_DELAY_SEC = 2


class GoogleAuthError(Exception):
    """Raised when OAuth credential loading or refresh fails."""


def get_oauth_credentials(
    *,
    scopes: Sequence[str],
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> Credentials:
    """
    Loads cached user credentials from token_path or runs an OAuth browser flow.

    - credentials_path: OAuth client JSON downloaded from Google Cloud Console
    - token_path: cached user tokens created after first run
    """
    creds: Optional[Credentials] = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes=list(scopes))

    if creds and creds.expired and creds.refresh_token:
        last_err: Optional[Exception] = None
        for attempt in range(_REFRESH_RETRIES):
            try:
                creds.refresh(Request())
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt < _REFRESH_RETRIES - 1:
                    time.sleep(_REFRESH_RETRY_DELAY_SEC)
        if last_err is not None:
            raise GoogleAuthError(f"Failed to refresh OAuth token: {last_err}") from last_err

    if not creds or not creds.valid:
        if not os.path.exists(credentials_path):
            raise GoogleAuthError(
                f"Missing OAuth client file: {credentials_path}. "
                "Create OAuth credentials and download the JSON."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, scopes=list(scopes)
            )
            creds = flow.run_local_server(port=0)
        except Exception as e:
            raise GoogleAuthError(f"OAuth login failed: {e}") from e

        try:
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        except Exception as e:
            raise GoogleAuthError(f"Failed to write token file: {token_path}: {e}") from e

    return creds
