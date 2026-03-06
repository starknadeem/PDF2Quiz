from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pdfplumber


class PdfExtractionError(Exception):
    pass


class McqParsingError(Exception):
    pass


@dataclass(frozen=True)
class MCQ:
    number: int
    question: str
    options: List[str]
    answer: Optional[str] = None
    explanation: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "question": self.question,
            "options": list(self.options),
            "answer": self.answer,
            "explanation": self.explanation,
        }


def extract_text_from_pdf_page(pdf_path: str, page_number: int) -> str:
    """
    Extract text from a 1-indexed page number using pdfplumber.
    """
    if page_number < 1:
        raise PdfExtractionError(f"Invalid page number: {page_number}. Page numbers start at 1.")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            if page_number > total_pages:
                raise PdfExtractionError(
                    f"Page out of range: {page_number}. PDF has {total_pages} pages."
                )
            page = pdf.pages[page_number - 1]
            text = page.extract_text() or ""
            text = text.strip()
            if not text:
                raise PdfExtractionError(
                    f"No extractable text found on page {page_number}. "
                    "The page may be scanned or contain only images."
                )
            return text
    except FileNotFoundError as e:
        raise PdfExtractionError(f"Invalid PDF path: {pdf_path}") from e
    except PdfExtractionError:
        raise
    except Exception as e:  # pragma: no cover
        raise PdfExtractionError(f"Failed to read PDF: {e}") from e


_Q_START_LINE_RE = re.compile(
    r"^\s*(?:Q\s*[-\.]?\s*)?(\d+)\s*[\.\)\:]\s*(.*\S)?\s*$", re.IGNORECASE
)
_Q_ONLY_LINE_RE = re.compile(r"^\s*Q\s*[-\.]?\s*(\d+)\s*$", re.IGNORECASE)
_OPT_LINE_RE_1 = re.compile(r"^\s*(?:[A-Ha-h])\s*[\)\.\:\-]\s*(.*\S)\s*$")
_OPT_LINE_RE_2 = re.compile(r"^\s*\(\s*(?:[A-Ha-h])\s*\)\s*(.*\S)\s*$")
_OPT_LINE_LABEL_RE = re.compile(r"^\s*([A-Ha-h])\s*[\)\.\:\-]\s*(.*\S)\s*$")

_Q_START_ANYWHERE_RE = re.compile(
    r"(?:(?<=\n)|^|\s)(?:Q\s*[-\.]?\s*)?(\d{1,5})\s*[\.\)]\s+",
    re.IGNORECASE,
)
_OPT_ANYWHERE_RE = re.compile(r"(?:(?<=\n)|^|\s)(?:\(\s*([A-Ha-h])\s*\)|([A-Ha-h]))\s*[\)\.\:\-]\s*")

_ANSWER_RE = re.compile(r"^\s*ANSWER\s*:?\s*(.*\S)?\s*$", re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"^\s*EXPLANATION\s*:?\s*(.*\S)?\s*$", re.IGNORECASE)

_WATERMARK_URL_RE = re.compile(r"(https?://\S+|t\.me/\S+)", re.IGNORECASE)


def _normalize_ws(s: str) -> str:
    # Keep newlines (sometimes meaningful), but collapse long runs of spaces/tabs.
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    # Remove watermark URLs anywhere in the text (inline or on their own line).
    s = _WATERMARK_URL_RE.sub("", s)
    return s.strip()


def _clean_footer_lines(lines: List[str]) -> List[str]:
    cleaned: List[str] = []
    for ln in lines:
        s = (ln or "").strip()
        if not s:
            continue
        if s.lower().startswith("http://") or s.lower().startswith("https://"):
            continue
        if s.lower().startswith("t.me/"):
            continue
        if re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", s, flags=re.IGNORECASE):
            continue
        cleaned.append(s)
    return cleaned


def parse_mcqs_from_text(text: str, start: int, end: int) -> List[MCQ]:
    """
    Parse MCQs from extracted text.

    Expected format:
      21. Question?
          A) Option
          B) Option
          C) Option
          D) Option
    """
    if start > end:
        raise McqParsingError(f"Invalid range: start ({start}) > end ({end}).")

    text = _normalize_ws(text)

    mcqs = _parse_mcqs_line_based(text, start, end)
    if mcqs:
        return mcqs

    mcqs = _parse_mcqs_token_based(text, start, end)
    if not mcqs:
        raise McqParsingError(
            "No MCQs parsed from the page using the expected format. "
            "Check that the page and formatting match the assumptions."
        )
    return mcqs


def _parse_mcqs_line_based(text: str, start: int, end: int) -> List[MCQ]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    mcqs: List[MCQ] = []

    current_num: int | None = None
    current_q_lines: List[str] = []
    current_opts: List[str] = []
    current_answer_lines: List[str] = []
    current_expl_lines: List[str] = []
    mode: str = "preamble"  # question | options | answer | explanation

    def flush() -> None:
        nonlocal current_num, current_q_lines, current_opts
        nonlocal current_answer_lines, current_expl_lines, mcqs, mode
        if current_num is None:
            return
        q_text = " ".join(s.strip() for s in current_q_lines if s.strip()).strip()
        answer = None
        expl = None
        ans_lines = _clean_footer_lines(current_answer_lines)
        if ans_lines:
            answer = ans_lines[0].strip()
        expl_lines = _clean_footer_lines(current_expl_lines)
        if expl_lines:
            expl = "\n".join(expl_lines).strip()

        if start <= current_num <= end:
            # Only include questions that look like real MCQs (options + answer key)
            if q_text and len(current_opts) >= 1 and answer:
                mcqs.append(
                    MCQ(
                        number=current_num,
                        question=q_text,
                        options=list(current_opts),
                        answer=answer,
                        explanation=expl,
                    )
                )
        current_num = None
        current_q_lines = []
        current_opts = []
        current_answer_lines = []
        current_expl_lines = []
        mode = "preamble"

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        am = _ANSWER_RE.match(line)
        if am and current_num is not None:
            mode = "answer"
            remainder = (am.group(1) or "").strip()
            if remainder:
                current_answer_lines.append(remainder)
            continue

        em = _EXPLANATION_RE.match(line)
        if em and current_num is not None:
            mode = "explanation"
            remainder = (em.group(1) or "").strip()
            if remainder:
                current_expl_lines.append(remainder)
            continue

        qonly = _Q_ONLY_LINE_RE.match(line)
        if qonly:
            # New question begins; flush previous.
            flush()
            current_num = int(qonly.group(1))
            current_q_lines = []
            current_opts = []
            current_answer_lines = []
            current_expl_lines = []
            mode = "question"
            continue

        qmatch = _Q_START_LINE_RE.match(line)
        if qmatch:
            flush()
            current_num = int(qmatch.group(1))
            remainder = (qmatch.group(2) or "").strip()
            current_q_lines = [remainder] if remainder else []
            current_opts = []
            current_answer_lines = []
            current_expl_lines = []
            mode = "question"
            continue

        if current_num is None:
            # Ignore preamble text before the first question we can detect.
            continue

        if mode in ("answer", "explanation"):
            if mode == "answer":
                current_answer_lines.append(line)
            else:
                current_expl_lines.append(line)
            continue

        lmatch = _OPT_LINE_LABEL_RE.match(line)
        if lmatch:
            mode = "options"
            current_opts.append(lmatch.group(2).strip())
            continue

        omatch = _OPT_LINE_RE_1.match(line) or _OPT_LINE_RE_2.match(line)
        if omatch:
            mode = "options"
            current_opts.append(omatch.group(1).strip())
            continue

        # Continuation of question text (sometimes wraps to next line).
        # Also allows for explanations or footers; we treat them as question text
        # until options begin.
        if mode != "options":
            current_q_lines.append(line)
        else:
            # If options started and we see a non-option line, keep it by appending
            # to the last option (some PDFs wrap options).
            current_opts[-1] = (current_opts[-1] + " " + line).strip()

    flush()

    return mcqs


def _parse_mcqs_token_based(text: str, start: int, end: int) -> List[MCQ]:
    """
    More robust parser for PDFs where line breaks are missing or columns are merged.
    It finds question starts like "21. " anywhere in the text and then extracts
    options like "A) " / "b) " / "C. " within each question block.
    """
    mcqs: List[MCQ] = []
    starts = list(_Q_START_ANYWHERE_RE.finditer(text))
    if not starts:
        return mcqs

    answer_marker = re.compile(r"\bANSWER\s*:?\s*", re.IGNORECASE)
    expl_marker = re.compile(r"\bEXPLANATION\s*:?\s*", re.IGNORECASE)

    for i, m in enumerate(starts):
        q_num = int(m.group(1))
        block_start = m.end()
        block_end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        block = text[block_start:block_end].strip()
        if not (start <= q_num <= end):
            continue

        answer_text = None
        explanation = None
        main_block = block

        am = answer_marker.search(block)
        if am:
            main_block = block[: am.start()].strip()
            after_answer = block[am.end() :].strip()
            em = expl_marker.search(after_answer)
            if em:
                answer_part = after_answer[: em.start()].strip()
                expl_part = after_answer[em.end() :].strip()
            else:
                answer_part = after_answer.strip()
                expl_part = ""

            ans_lines = _clean_footer_lines(answer_part.splitlines())
            if ans_lines:
                answer_text = ans_lines[0].strip()

            expl_lines = _clean_footer_lines(expl_part.splitlines())
            if expl_lines:
                explanation = "\n".join(expl_lines).strip()

        opt_matches = list(_OPT_ANYWHERE_RE.finditer(main_block))
        if not opt_matches:
            continue

        first_opt = opt_matches[0].start()
        q_text = main_block[:first_opt].strip()
        if not q_text:
            continue

        options: List[str] = []
        for j, om in enumerate(opt_matches):
            opt_text_start = om.end()
            opt_text_end = (
                opt_matches[j + 1].start() if j + 1 < len(opt_matches) else len(main_block)
            )
            opt_text = main_block[opt_text_start:opt_text_end].strip()
            if opt_text:
                options.append(opt_text)

        if options and answer_text:
            mcqs.append(
                MCQ(
                    number=q_num,
                    question=q_text,
                    options=options,
                    answer=answer_text,
                    explanation=explanation,
                )
            )

    return mcqs


def find_pages_containing_question(
    pdf_path: str,
    question_number: int,
    *,
    max_hits: int = 10,
    coarse_step: int = 25,
    require_answer_marker: bool = False,
) -> List[int]:
    """
    Returns 1-indexed page numbers that appear to contain the given question number.
    Useful when the human page number doesn't match the actual PDF page index.
    """
    num = str(question_number)
    pat = re.compile(
        rf"(?:^|\s){re.escape(num)}\s*[.)]\s|(?:^|\s)Q\s*[-\.]?\s*{re.escape(num)}\b",
        re.IGNORECASE,
    )
    hits: List[int] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            step = max(1, int(coarse_step))

            # Coarse scan: check every Nth page to find regions.
            coarse_pages: List[int] = []
            for p in range(1, total + 1, step):
                t = pdf.pages[p - 1].extract_text() or ""
                if require_answer_marker and not re.search(
                    r"\bANSWER\b|\bEXPLANATION\b", t, flags=re.IGNORECASE
                ):
                    continue
                if pat.search(t):
                    coarse_pages.append(p)
                    if len(coarse_pages) >= max_hits:
                        break

            # Refine: scan within each coarse window to find exact pages.
            for p in coarse_pages:
                start_p = p
                end_p = min(total, p + step - 1)
                for idx in range(start_p, end_p + 1):
                    t = pdf.pages[idx - 1].extract_text() or ""
                    if require_answer_marker and not re.search(
                        r"\bANSWER\b|\bEXPLANATION\b", t, flags=re.IGNORECASE
                    ):
                        continue
                    if pat.search(t):
                        if idx not in hits:
                            hits.append(idx)
                            if len(hits) >= max_hits:
                                return hits
    except FileNotFoundError as e:
        raise PdfExtractionError(f"Invalid PDF path: {pdf_path}") from e
    except Exception as e:  # pragma: no cover
        raise PdfExtractionError(f"Failed to read PDF: {e}") from e
    return hits

