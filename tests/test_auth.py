"""Unit tests for auth scope-handling and re-auth behavior."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from auth import get_oauth_credentials


def test_missing_required_scopes_forces_oauth_flow(tmp_path):
    """If token scopes do not cover requested scopes, run fresh OAuth flow."""
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "credentials.json"

    token_path.write_text(
        json.dumps(
            {
                "token": "abc",
                "refresh_token": "rt",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "x",
                "client_secret": "y",
                "scopes": ["https://www.googleapis.com/auth/forms.body"],
            }
        ),
        encoding="utf-8",
    )
    credentials_path.write_text("{}", encoding="utf-8")

    flow = MagicMock()
    new_creds = MagicMock(valid=True)
    new_creds.to_json.return_value = '{"token":"new"}'
    flow.run_local_server.return_value = new_creds

    with patch("auth.Credentials.from_authorized_user_file") as mock_from_file, patch(
        "auth.InstalledAppFlow.from_client_secrets_file", return_value=flow
    ) as mock_flow:
        creds = get_oauth_credentials(
            scopes=[
                "https://www.googleapis.com/auth/forms.body",
                "https://www.googleapis.com/auth/classroom.coursework.students",
            ],
            credentials_path=str(credentials_path),
            token_path=str(token_path),
        )

    assert creds is new_creds
    mock_from_file.assert_not_called()
    mock_flow.assert_called_once()


def test_invalid_scope_refresh_falls_back_to_oauth(tmp_path):
    """invalid_scope refresh errors should trigger full OAuth flow."""
    token_path = tmp_path / "token.json"
    credentials_path = tmp_path / "credentials.json"

    token_path.write_text(
        json.dumps(
            {
                "token": "abc",
                "refresh_token": "rt",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "x",
                "client_secret": "y",
                "scopes": ["https://www.googleapis.com/auth/forms.body"],
            }
        ),
        encoding="utf-8",
    )
    credentials_path.write_text("{}", encoding="utf-8")

    old_creds = MagicMock()
    old_creds.expired = True
    old_creds.refresh_token = "rt"
    old_creds.valid = False
    old_creds.refresh.side_effect = Exception("invalid_scope: Bad Request")

    flow = MagicMock()
    new_creds = MagicMock(valid=True)
    new_creds.to_json.return_value = '{"token":"new"}'
    flow.run_local_server.return_value = new_creds

    with patch("auth.Credentials.from_authorized_user_file", return_value=old_creds), patch(
        "auth.InstalledAppFlow.from_client_secrets_file", return_value=flow
    ) as mock_flow:
        creds = get_oauth_credentials(
            scopes=["https://www.googleapis.com/auth/forms.body"],
            credentials_path=str(credentials_path),
            token_path=str(token_path),
        )

    assert creds is new_creds
    assert old_creds.refresh.call_count == 3
    mock_flow.assert_called_once()
