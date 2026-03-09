"""Unit tests for classroom_uploader payload behavior."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from classroom_uploader import _normalize_classroom_id, create_quiz_assignment_with_link


@patch("classroom_uploader.build")
@patch("classroom_uploader.get_oauth_credentials")
def test_create_assignment_does_not_set_scheduled_time_by_default(
    mock_get_creds, mock_build
):
    """Default payload should not include scheduledTime (API may reject 'now')."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.courses.return_value.courseWork.return_value.create.return_value.execute.return_value = {
        "id": "cw123"
    }
    mock_build.return_value = mock_service

    created_id = create_quiz_assignment_with_link(
        classroom_id="123456",
        title="Quiz",
        form_url="https://docs.google.com/forms/d/e/abc/viewform",
        draft=True,
    )

    assert created_id == "cw123"
    body = mock_service.courses.return_value.courseWork.return_value.create.call_args[1]["body"]
    assert "scheduledTime" not in body


@patch("classroom_uploader.build")
@patch("classroom_uploader.get_oauth_credentials")
def test_create_assignment_due_date_adds_due_date_and_time(mock_get_creds, mock_build):
    """Valid due date should set dueDate and dueTime fields."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.courses.return_value.courseWork.return_value.create.return_value.execute.return_value = {
        "id": "cw999"
    }
    mock_build.return_value = mock_service

    create_quiz_assignment_with_link(
        classroom_id="123456",
        title="Quiz",
        form_url="https://docs.google.com/forms/d/e/abc/viewform",
        due_date="2026-03-20",
    )

    body = mock_service.courses.return_value.courseWork.return_value.create.call_args[1]["body"]
    assert body["dueDate"] == {"year": 2026, "month": 3, "day": 20}
    assert body["dueTime"] == {"hours": 23, "minutes": 59, "seconds": 0}


def test_normalize_classroom_id_decodes_base64_numeric():
    assert _normalize_classroom_id("ODUwMTUwNDcxNDI5") == "850150471429"
    assert _normalize_classroom_id("850150471429") == "850150471429"


@patch("classroom_uploader.build")
@patch("classroom_uploader.get_oauth_credentials")
def test_create_assignment_uses_normalized_course_id(mock_get_creds, mock_build):
    """Encoded course IDs should be decoded before API call."""
    mock_get_creds.return_value = MagicMock()
    mock_service = MagicMock()
    mock_service.courses.return_value.courseWork.return_value.create.return_value.execute.return_value = {
        "id": "cw555"
    }
    mock_build.return_value = mock_service

    create_quiz_assignment_with_link(
        classroom_id="ODUwMTUwNDcxNDI5",
        title="Quiz",
        form_url="https://docs.google.com/forms/d/e/abc/viewform",
    )

    call_kwargs = mock_service.courses.return_value.courseWork.return_value.create.call_args[1]
    assert call_kwargs["courseId"] == "850150471429"
