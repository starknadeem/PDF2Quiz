from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from auth import GoogleAuthError, get_oauth_credentials


class GoogleFormsError(Exception):
    pass


FORMS_SCOPES: Tuple[str, ...] = (
    "https://www.googleapis.com/auth/forms.body",
)


def _single_line(s: str) -> str:
    """Collapse newlines and extra spaces so Google Forms API accepts the text."""
    return " ".join((s or "").strip().split())


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
    try:
        creds = get_oauth_credentials(
            scopes=FORMS_SCOPES, credentials_path=credentials_path, token_path=token_path
        )
    except GoogleAuthError as e:
        raise GoogleFormsError(str(e)) from e

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
            q_text = _single_line(f'{mcq["number"]}. {mcq["question"]}')
            options = [_single_line(opt) for opt in mcq["options"]]
            answer = (mcq.get("answer") or "").strip()
            explanation = (mcq.get("explanation") or "").strip()

            def norm(s: str) -> str:
                return " ".join((s or "").strip().split()).lower()

            correct_value = None
            if answer:
                # Accept answer as a letter (A/B/C/...) or as exact option text.
                m = re.match(r"^\s*\(?\s*([A-Ha-h])\s*\)?\s*[\.\)]?\s*$", answer)
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
                when_right = _single_line(explanation if explanation else "Correct.")
                when_wrong = (
                    f"Correct answer: {correct_value}. {_single_line(explanation)}"
                    if explanation
                    else f"Correct answer: {correct_value}"
                )
                question_obj["grading"] = {
                    "pointValue": 1,
                    "correctAnswers": {"answers": [{"value": correct_value}]},
                    "whenRight": {"text": when_right},
                    "whenWrong": {"text": when_wrong},
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

