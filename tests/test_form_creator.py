"""Unit tests for form_creator module (answer matching and API flow with mocks)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from auth import GoogleAuthError, get_oauth_credentials
from form_creator import GoogleFormsError, create_quiz_form


def test_get_oauth_credentials_missing_client_file():
    with pytest.raises(GoogleAuthError, match="Missing OAuth client file"):
        get_oauth_credentials(
            scopes=["https://www.googleapis.com/auth/forms.body"],
            credentials_path="/nonexistent/credentials.json",
            token_path="/nonexistent/token.json",
        )


@patch("form_creator.build")
@patch("form_creator.get_oauth_credentials")
def test_create_quiz_form_answer_as_letter(mock_get_creds, mock_build):
    """Answer given as 'C' should set correct option (third option)."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.forms.return_value.create.return_value.execute.return_value = {
        "formId": "form123",
        "responderUri": "https://docs.google.com/forms/d/form123/viewform",
    }
    mock_service.forms.return_value.batchUpdate.return_value.execute.return_value = {}
    mock_build.return_value = mock_service

    mcqs = [
        {
            "number": 1,
            "question": "Capital of France?",
            "options": ["Berlin", "Madrid", "Paris", "Rome"],
            "answer": "C",
            "explanation": "Paris.",
        }
    ]
    url = create_quiz_form(title="Quiz", mcqs=mcqs)
    assert "form123" in url

    batch_body = mock_service.forms.return_value.batchUpdate.call_args[1]["body"]
    requests = batch_body["requests"]
    # First request is updateSettings; then createItem for each question.
    create_requests = [r for r in requests if "createItem" in r]
    assert len(create_requests) == 1
    q = create_requests[0]["createItem"]["item"]["questionItem"]["question"]
    assert "grading" in q
    assert q["grading"]["correctAnswers"]["answers"][0]["value"] == "Paris"


@patch("form_creator.build")
@patch("form_creator.get_oauth_credentials")
def test_create_quiz_form_answer_as_option_text(mock_get_creds, mock_build):
    """Answer given as exact option text should match."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.forms.return_value.create.return_value.execute.return_value = {
        "formId": "form456",
        "responderUri": "https://docs.google.com/forms/d/form456/viewform",
    }
    mock_service.forms.return_value.batchUpdate.return_value.execute.return_value = {}
    mock_build.return_value = mock_service

    mcqs = [
        {
            "number": 1,
            "question": "Pick one.",
            "options": ["Alpha", "Beta", "Gamma"],
            "answer": "Gamma",
            "explanation": None,
        }
    ]
    create_quiz_form(title="Quiz", mcqs=mcqs)

    batch_body = mock_service.forms.return_value.batchUpdate.call_args[1]["body"]
    requests = batch_body["requests"]
    create_requests = [r for r in requests if "createItem" in r]
    assert len(create_requests) == 1
    q = create_requests[0]["createItem"]["item"]["questionItem"]["question"]
    assert q["grading"]["correctAnswers"]["answers"][0]["value"] == "Gamma"


@patch("form_creator.build")
@patch("form_creator.get_oauth_credentials")
def test_create_quiz_form_no_answer_no_grading(mock_get_creds, mock_build):
    """When answer is missing, question item has no grading."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.forms.return_value.create.return_value.execute.return_value = {
        "formId": "form789",
        "responderUri": "https://docs.google.com/forms/d/form789/viewform",
    }
    mock_service.forms.return_value.batchUpdate.return_value.execute.return_value = {}
    mock_build.return_value = mock_service

    mcqs = [
        {
            "number": 1,
            "question": "Open question.",
            "options": ["A", "B"],
            "answer": "",
            "explanation": None,
        }
    ]
    create_quiz_form(title="Quiz", mcqs=mcqs)

    batch_body = mock_service.forms.return_value.batchUpdate.call_args[1]["body"]
    requests = batch_body["requests"]
    create_requests = [r for r in requests if "createItem" in r]
    assert len(create_requests) == 1
    q = create_requests[0]["createItem"]["item"]["questionItem"]["question"]
    assert "grading" not in q
