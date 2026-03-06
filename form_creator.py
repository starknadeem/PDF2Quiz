from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleFormsError(Exception):
    pass


FORMS_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/forms.body",
)


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
        try:
            creds.refresh(Request())
        except Exception as e:
            raise GoogleFormsError(f"Failed to refresh OAuth token: {e}") from e

    if not creds or not creds.valid:
        if not os.path.exists(credentials_path):
            raise GoogleFormsError(
                f"Missing OAuth client file: {credentials_path}. "
                "Create OAuth credentials and download the JSON."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes=list(scopes))
            creds = flow.run_local_server(port=0)
        except Exception as e:
            raise GoogleFormsError(f"OAuth login failed: {e}") from e

        try:
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        except Exception as e:
            raise GoogleFormsError(f"Failed to write token file: {token_path}: {e}") from e

    return creds


def create_quiz_form(
    *,
    title: str,
    mcqs: Iterable[dict],
    credentials_path: str = "credentials.json",
    token_path: str = "token.json",
) -> str:
    """
    Creates a Google Form configured as a quiz, adds MCQ items, returns the responder URL.

    Each mcq dict must have keys:
      - number (int)
      - question (str)
      - options (list[str])
      - answer (str | None)
      - explanation (str | None)
    """
    creds = get_oauth_credentials(
        scopes=FORMS_SCOPES, credentials_path=credentials_path, token_path=token_path
    )

    try:
        service = build("forms", "v1", credentials=creds, cache_discovery=False)

        form = service.forms().create(body={"info": {"title": title}}).execute()
        form_id = form["formId"]
        responder_url = form.get("responderUri")

        requests: List[dict] = []

        # Turn on quiz mode
        requests.append(
            {
                "updateSettings": {
                    "settings": {"quizSettings": {"isQuiz": True}},
                    "updateMask": "quizSettings.isQuiz",
                }
            }
        )

        # Add items
        index = 0
        for mcq in mcqs:
            q_text = f'{mcq["number"]}. {mcq["question"]}'.strip()
            options = mcq["options"]
            answer = (mcq.get("answer") or "").strip()
            explanation = (mcq.get("explanation") or "").strip()

            def norm(s: str) -> str:
                return " ".join((s or "").strip().split()).lower()

            correct_value = None
            if answer:
                # Accept answer as a letter (A/B/C/...) or as exact option text.
                import re as _re

                m = _re.match(r"^\s*\(?\s*([A-Ha-h])\s*\)?\s*[\.\)]?\s*$", answer)
                if m:
                    idx = ord(m.group(1).upper()) - ord("A")
                    if 0 <= idx < len(options):
                        correct_value = options[idx]
                else:
                    ans_n = norm(answer)
                    for opt in options:
                        if norm(opt) == ans_n:
                            correct_value = opt
                            break

            question_obj = {
                "required": True,
                "choiceQuestion": {
                    "type": "RADIO",
                    "options": [{"value": opt} for opt in options],
                    "shuffle": False,
                },
            }

            if correct_value:
                question_obj["grading"] = {
                    "pointValue": 1,
                    "correctAnswers": {"answers": [{"value": correct_value}]},
                    "whenRight": {"text": explanation if explanation else "Correct."},
                    "whenWrong": {
                        "text": (
                            f"Correct answer: {correct_value}\n\n{explanation}"
                            if explanation
                            else f"Correct answer: {correct_value}"
                        )
                    },
                }

            requests.append(
                {
                    "createItem": {
                        "item": {
                            "title": q_text,
                            "questionItem": {
                                "question": question_obj
                            },
                        },
                        "location": {"index": index},
                    }
                }
            )
            index += 1

        service.forms().batchUpdate(formId=form_id, body={"requests": requests}).execute()

        if not responder_url:
            # Fallback: build a responder URL format (not guaranteed but usually works)
            responder_url = f"https://docs.google.com/forms/d/{form_id}/viewform"

        return responder_url

    except HttpError as e:
        raise GoogleFormsError(f"Google Forms API error: {e}") from e
    except KeyError as e:
        raise GoogleFormsError(f"Unexpected Google Forms API response missing key: {e}") from e
    except Exception as e:
        raise GoogleFormsError(f"Failed to create Google Form: {e}") from e

