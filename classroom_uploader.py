from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from auth import GoogleAuthError, get_oauth_credentials


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
    due_date: Optional[str] = None,
    max_points: Optional[int] = None,
    draft: bool = False,
) -> str:
    """
    Creates a Classroom assignment that links to the generated Google Form.

    Note: Classroom API does not allow setting Material.form directly (read-only).
    Using a normal link material is supported and works for Forms URLs.

    due_date: optional date string YYYY-MM-DD (UTC); if set, due time is 23:59:00 UTC.
    max_points: optional maximum grade (non-negative integer).
    draft: if True, create as DRAFT; otherwise PUBLISHED.

    Returns the created coursework ID.
    """
    try:
        creds = get_oauth_credentials(
            scopes=CLASSROOM_SCOPES,
            credentials_path=credentials_path,
            token_path=token_path,
        )
    except GoogleAuthError as e:
        raise GoogleClassroomError(str(e)) from e

    now = datetime.now(timezone.utc)
    course_work = {
        "title": title,
        "description": description or "Quiz generated from PDF MCQs.",
        "materials": [{"link": {"url": form_url, "title": "Google Form Quiz"}}],
        "workType": "ASSIGNMENT",
        "state": "DRAFT" if draft else "PUBLISHED",
        "scheduledTime": now.isoformat(),
    }
    if max_points is not None and max_points >= 0:
        course_work["maxPoints"] = max_points
    if due_date:
        # dueDate: { year, month, day }; dueTime required if dueDate set (use 23:59 UTC).
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", due_date.strip())
        if m:
            course_work["dueDate"] = {
                "year": int(m.group(1)),
                "month": int(m.group(2)),
                "day": int(m.group(3)),
            }
            course_work["dueTime"] = {"hours": 23, "minutes": 59, "seconds": 0}

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

