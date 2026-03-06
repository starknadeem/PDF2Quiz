from __future__ import annotations

import argparse
import sys

from classroom_uploader import GoogleClassroomError, create_quiz_assignment_with_link
from form_creator import GoogleFormsError, create_quiz_form
from pdf_parser import (
    McqParsingError,
    PdfExtractionError,
    extract_text_from_pdf_page,
    find_pages_containing_question,
    parse_mcqs_from_text,
)


def _collect_mcqs_forward(
    *, pdf_path: str, start_page: int, start: int, end: int, max_pages: int = 15
) -> list:
    """
    Collect MCQs across consecutive pages starting at start_page until we have the
    full start-end range, or we hit max_pages.
    """
    combined_parts: list[str] = []
    best: list = []
    for p in range(start_page, start_page + max_pages):
        try:
            text = extract_text_from_pdf_page(pdf_path, p)
        except PdfExtractionError:
            break
        combined_parts.append(text)
        combined = "\n".join(combined_parts)
        try:
            mcqs = parse_mcqs_from_text(combined, start, end)
            best = mcqs
            if len(best) >= (end - start + 1):
                break
        except McqParsingError:
            # Keep accumulating pages; question/options/answer often spill across pages.
            continue
    return best


def _fill_missing_mcqs_by_search(*, pdf_path: str, start: int, end: int, current: list) -> list:
    collected = {m.number: m for m in current}
    missing = [n for n in range(start, end + 1) if n not in collected]
    for n in missing:
        pages = find_pages_containing_question(
            pdf_path, n, max_hits=5, coarse_step=25, require_answer_marker=True
        )
        for p in pages:
            try:
                text = extract_text_from_pdf_page(pdf_path, p)
                mcqs = parse_mcqs_from_text(text, start, end)
                for m in mcqs:
                    collected[m.number] = m
            except Exception:
                continue
            if n in collected:
                break
    return [collected[k] for k in sorted(collected.keys())]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a Google Form quiz from a PDF page of MCQs.")
    p.add_argument("--pdf", required=True, help="Path to the PDF file containing MCQs")
    p.add_argument("--page", required=True, type=int, help="1-indexed page number in the PDF")
    p.add_argument("--start", required=True, type=int, help="Starting MCQ number (inclusive)")
    p.add_argument("--end", required=True, type=int, help="Ending MCQ number (inclusive)")
    p.add_argument("--title", required=True, help="Google Form title")

    p.add_argument(
        "--classroom_id",
        required=False,
        default=None,
        help="Optional Google Classroom course ID to create an assignment",
    )
    p.add_argument(
        "--credentials",
        required=False,
        default="credentials.json",
        help="Path to OAuth client JSON (default: credentials.json)",
    )
    p.add_argument(
        "--token",
        required=False,
        default="token.json",
        help="Path to cached OAuth token JSON (default: token.json)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        best_page = None
        text = extract_text_from_pdf_page(args.pdf, args.page)
        try:
            mcqs = parse_mcqs_from_text(text, args.start, args.end)
        except McqParsingError:
            # Common real-world issue: the human-visible "page 5" doesn't match the PDF page index.
            candidates = find_pages_containing_question(args.pdf, args.start)
            best_mcqs = []

            for p in candidates[:10]:
                try:
                    cand_text = extract_text_from_pdf_page(args.pdf, p)
                    cand_mcqs = parse_mcqs_from_text(cand_text, args.start, args.end)
                    if len(cand_mcqs) > len(best_mcqs):
                        best_page = p
                        best_mcqs = cand_mcqs
                except Exception:
                    continue

            if best_page is not None and best_page != args.page and best_mcqs:
                print(
                    f"Warning: page {args.page} did not parse for range {args.start}-{args.end}. "
                    f"Using detected page {best_page} instead.",
                    file=sys.stderr,
                )
                text = extract_text_from_pdf_page(args.pdf, best_page)
                mcqs = best_mcqs
            elif candidates:
                raise McqParsingError(
                    f"Could not parse MCQs on page {args.page} for range {args.start}-{args.end}. "
                    f"Question {args.start} appears on page(s): {candidates}. "
                    "Re-run with --page set to one of these."
                )
            else:
                raise

        # If the range spans multiple pages, continue forward to collect more.
        if mcqs:
            start_page = best_page if best_page is not None else args.page
            mcqs = _collect_mcqs_forward(
                pdf_path=args.pdf, start_page=start_page, start=args.start, end=args.end
            )
            if len(mcqs) < (args.end - args.start + 1):
                mcqs = _fill_missing_mcqs_by_search(
                    pdf_path=args.pdf, start=args.start, end=args.end, current=mcqs
                )
        expected_count = args.end - args.start + 1
        if len(mcqs) != expected_count:
            parsed_nums = [m.number for m in mcqs]
            print(
                f"Warning: parsed {len(mcqs)} question(s) in range {args.start}-{args.end} "
                f"(expected {expected_count}). Parsed numbers: {parsed_nums}",
                file=sys.stderr,
            )
        mcq_dicts = [m.to_dict() for m in mcqs]

        form_url = create_quiz_form(
            title=args.title,
            mcqs=mcq_dicts,
            credentials_path=args.credentials,
            token_path=args.token,
        )

        print("Form created successfully")
        print(f"Form URL: {form_url}")

        if args.classroom_id:
            create_quiz_assignment_with_link(
                classroom_id=args.classroom_id,
                title=args.title,
                form_url=form_url,
                credentials_path=args.credentials,
                token_path=args.token,
            )
            print("Quiz assignment created successfully.")

        return 0

    except (PdfExtractionError, McqParsingError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except (GoogleFormsError, GoogleClassroomError) as e:
        print(f"Google API Error: {e}", file=sys.stderr)
        return 3
    except Exception as e:  # pragma: no cover
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

