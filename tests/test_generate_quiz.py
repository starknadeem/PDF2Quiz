"""Integration-style tests for generate_quiz (mocked PDF and Google APIs)."""
from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from generate_quiz import _parse_missing_page_input, main
from pdf_parser import MCQ


@patch("generate_quiz.create_quiz_form")
@patch("generate_quiz.parse_mcqs_from_text")
@patch("generate_quiz.extract_text_from_pdf_page")
def test_main_preview_exits_without_calling_forms(
    mock_extract, mock_parse, mock_create_form
):
    """When --preview is passed, no Google Form is created."""
    mock_extract.return_value = "1. Q? A) x B) y ANSWER: A"
    mock_parse.return_value = [
        MCQ(1, "Q?", ["x", "y"], "A", None),
    ]
    mock_create_form.return_value = "https://forms.example.com/viewform"
    exit_code = main(
        [
            "--pdf", "dummy.pdf",
            "--page", "1",
            "--start", "1",
            "--end", "1",
            "--title", "Test",
            "--preview",
        ]
    )
    assert exit_code == 0
    mock_create_form.assert_not_called()


@patch("generate_quiz.create_quiz_form")
@patch("generate_quiz.extract_text_from_pdf_page")
def test_main_invalid_range_fails_fast(mock_extract, mock_create_form):
    """Invalid --start > --end should fail with exit 2 before calling Forms."""
    mock_extract.return_value = "1. Q? A) x ANSWER: A"
    exit_code = main(
        [
            "--pdf", "dummy.pdf",
            "--page", "1",
            "--start", "10",
            "--end", "5",
            "--title", "Test",
        ]
    )
    assert exit_code == 2
    mock_create_form.assert_not_called()


def test_parse_missing_page_input_accepts_valid_pairs_only():
    missing = [4, 7, 10]
    raw = "4=1090, 7:1092, 9=1000, x=1, 10=0"
    result = _parse_missing_page_input(raw, missing)
    assert result == {4: 1090, 7: 1092}


@patch("generate_quiz.create_quiz_form")
@patch("generate_quiz.find_pages_containing_question", return_value=[])
@patch("generate_quiz.parse_mcqs_from_text")
@patch("generate_quiz.extract_text_from_pdf_page")
def test_main_noninteractive_missing_questions_aborts_before_form(
    mock_extract, mock_parse, _mock_find_pages, mock_create_form
):
    """If questions are still missing and stdin is non-interactive, abort before form creation."""
    mock_extract.return_value = "1. Q? A) x B) y ANSWER: A"
    mock_parse.return_value = [MCQ(1, "Q1?", ["x", "y"], "A", None)]

    with patch.object(sys.stdin, "isatty", return_value=False):
        exit_code = main(
            [
                "--pdf", "dummy.pdf",
                "--page", "1",
                "--end-page", "1",
                "--start", "1",
                "--end", "2",
                "--title", "Test",
            ]
        )

    assert exit_code == 2
    mock_create_form.assert_not_called()
