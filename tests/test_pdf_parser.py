"""Unit tests for pdf_parser module."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from pdf_parser import (
    MCQ,
    McqParsingError,
    PdfExtractionError,
    extract_text_from_pdf_page,
    find_pages_containing_question,
    parse_mcqs_from_text,
)


# --- MCQ and to_dict ---
def test_mcq_to_dict():
    mcq = MCQ(
        number=1,
        question="What is 2+2?",
        options=["3", "4", "5"],
        answer="4",
        explanation="Basic math.",
    )
    d = mcq.to_dict()
    assert d["number"] == 1
    assert d["question"] == "What is 2+2?"
    assert d["options"] == ["3", "4", "5"]
    assert d["answer"] == "4"
    assert d["explanation"] == "Basic math."


# --- extract_text_from_pdf_page ---
def test_extract_text_invalid_page_zero():
    with pytest.raises(PdfExtractionError, match="Invalid page number.*start at 1"):
        extract_text_from_pdf_page("/nonexistent.pdf", 0)


def test_extract_text_file_not_found():
    with pytest.raises(PdfExtractionError, match="Invalid PDF path"):
        extract_text_from_pdf_page("/nonexistent/path/file.pdf", 1)


def test_extract_text_page_out_of_range():
    fake_pdf = MagicMock()
    fake_pdf.pages = [MagicMock()]
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        with pytest.raises(PdfExtractionError, match="Page out of range"):
            extract_text_from_pdf_page("/some/file.pdf", 2)


def test_extract_text_empty_page():
    fake_page = MagicMock()
    fake_page.extract_text.return_value = None
    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page]
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        with pytest.raises(PdfExtractionError, match="No extractable text"):
            extract_text_from_pdf_page("/some/file.pdf", 1)


def test_extract_text_success():
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "  21. What is the capital?\nA) Paris\nB) London  "
    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page]
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        text = extract_text_from_pdf_page("/some/file.pdf", 1)
    assert "21." in text
    assert "Paris" in text
    assert text == text.strip()


# --- parse_mcqs_from_text: line-based ---
SAMPLE_LINE_BASED = """
21. What is the capital of France?
    A) Berlin
    B) Madrid
    C) Paris
    D) Rome
ANSWER:
C
EXPLANATION:
Paris is the capital of France.
"""


def test_parse_mcqs_line_based_basic():
    mcqs = parse_mcqs_from_text(SAMPLE_LINE_BASED, 21, 21)
    assert len(mcqs) == 1
    assert mcqs[0].number == 21
    assert "capital" in mcqs[0].question
    assert mcqs[0].options == ["Berlin", "Madrid", "Paris", "Rome"]
    assert mcqs[0].answer == "C"
    assert "Paris is the capital" in (mcqs[0].explanation or "")


def test_parse_mcqs_line_based_range_filter():
    # Text only has Q21; asking for range 1-10 yields no in-range MCQs, so parser raises.
    with pytest.raises(McqParsingError, match="No MCQs parsed"):
        parse_mcqs_from_text(SAMPLE_LINE_BASED, 1, 10)
    mcqs = parse_mcqs_from_text(SAMPLE_LINE_BASED, 21, 30)
    assert len(mcqs) == 1
    assert mcqs[0].number == 21


def test_parse_mcqs_invalid_range():
    with pytest.raises(McqParsingError, match="Invalid range"):
        parse_mcqs_from_text(SAMPLE_LINE_BASED, 30, 21)


# --- parse_mcqs_from_text: token-based (no newlines) ---
SAMPLE_TOKEN_BASED = (
    "21. What is 2+2? A) 3 B) 4 C) 5 ANSWER: B EXPLANATION: Four."
)


def test_parse_mcqs_token_based():
    mcqs = parse_mcqs_from_text(SAMPLE_TOKEN_BASED, 21, 21)
    assert len(mcqs) == 1
    assert mcqs[0].number == 21
    assert "2+2" in mcqs[0].question
    assert mcqs[0].options == ["3", "4", "5"]
    assert mcqs[0].answer == "B"
    assert "Four" in (mcqs[0].explanation or "")


# --- Watermark / _normalize_ws (via parse) ---
SAMPLE_WITH_WATERMARK = """
1. Pick one. A) X B) Y ANSWER: A
t.me/something https://example.com
EXPLANATION: None.
"""


def test_watermark_removal():
    mcqs = parse_mcqs_from_text(SAMPLE_WITH_WATERMARK, 1, 1)
    assert len(mcqs) == 1
    assert mcqs[0].number == 1
    # Parser should still find question/options/answer; watermark lines stripped by _clean_footer_lines or normalized away
    assert mcqs[0].options == ["X", "Y"]


# --- find_pages_containing_question ---
def test_find_pages_containing_question_file_not_found():
    with pytest.raises(PdfExtractionError, match="Invalid PDF path"):
        find_pages_containing_question("/nonexistent.pdf", 1)


def test_find_pages_containing_question_finds_page():
    fake_pages = [
        MagicMock(extract_text=MagicMock(return_value="Other content")),
        MagicMock(extract_text=MagicMock(return_value="21. Question here A) x ANSWER: A")),
    ]
    fake_pdf = MagicMock()
    fake_pdf.pages = fake_pages
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        hits = find_pages_containing_question(
            "/some/file.pdf", 21, require_answer_marker=True, coarse_step=1
        )
    assert 2 in hits


def test_find_pages_containing_question_no_hits():
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "No question numbers here."
    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page]
    fake_pdf.__enter__ = MagicMock(return_value=fake_pdf)
    fake_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdf_parser.pdfplumber.open", return_value=fake_pdf):
        hits = find_pages_containing_question("/some/file.pdf", 99)
    assert hits == []


# --- Plausibility filter: list/table content dropped ---
SAMPLE_LIST_LIKE_MCQ = (
    """
21. Normal short question?
A) One
B) Two
C) Three
D) Four
ANSWER: B

22. """
    + "x" * 1201
    + """
A) One
B) Two
ANSWER: A
"""
)


def test_parse_filters_list_like_mcq():
    # Q22 has question length > 1200 chars → filtered out; only Q21 kept
    mcqs = parse_mcqs_from_text(SAMPLE_LIST_LIKE_MCQ, 21, 22)
    assert len(mcqs) == 1
    assert mcqs[0].number == 21
    assert "Normal short" in mcqs[0].question
