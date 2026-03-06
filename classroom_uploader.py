from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from form_creator import get_oauth_credentials


class GoogleClassroomError(Exception):
    pass


CLASSROOM_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
)


def create_quiz_assignment_with_link(
    *,
    classroom_id: str,
    title: str,
    form_url: str,
    description: Optional[str] = None,
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> str:
    """
    Creates a Classroom assignment that links to the generated Google Form.

    Note: Classroom API does not allow setting Material.form directly (read-only).
    Using a normal link material is supported and works for Forms URLs.

    Returns the created coursework ID.
    """
    creds = get_oauth_credentials(
        scopes=CLASSROOM_SCOPES, credentials_path=credentials_path, token_path=token_path
    )

    now = datetime.now(timezone.utc)
    # Keep it a draft by default? Requirement says "create a quiz assignment".
    # We'll publish immediately so teachers see it without extra steps.
    course_work = {
        "title": title,
        "description": description or "Quiz generated from PDF MCQs.",
        "materials": [{"link": {"url": form_url, "title": "Google Form Quiz"}}],
        "workType": "ASSIGNMENT",
        "state": "PUBLISHED",
        "scheduledTime": now.isoformat(),
    }

    try:
        service = build("classroom", "v1", credentials=creds, cache_discovery=False)
        created = (
            service.courses()
            .courseWork()
            .create(courseId=classroom_id, body=course_work)
            .execute()
        )
        return created["id"]
    except HttpError as e:
        raise GoogleClassroomError(f"Google Classroom API error: {e}") from e
    except KeyError as e:
        raise GoogleClassroomError(
            f"Unexpected Google Classroom API response missing key: {e}"
        ) from e
    except Exception as e:
        raise GoogleClassroomError(f"Failed to create Classroom assignment: {e}") from e

