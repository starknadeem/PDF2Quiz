from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from classroom_uploader import GoogleClassroomError, create_quiz_assignment_with_link
from form_creator import GoogleFormsError, create_quiz_form
from pdf_parser import (
    McqParsingError,
    PdfExtractionError,
    extract_text_from_pdf_page,
    find_pages_containing_question,
    get_question_start_positions,
    parse_mcqs_from_text,
)


def _collect_mcqs_forward(
    *,
    pdf_path: str,
    start_page: int,
    start: int,
    end: int,
    max_pages: int = 30,
    end_page: int | None = None,
    allow_no_answer: bool = False,
) -> list:
    """
    Collect MCQs across consecutive pages from start_page. Stops at end_page
    (if given) or after max_pages, so we don't pull in another section.
    """
    combined_parts: list[str] = []
    best: list = []
    last_page = end_page if end_page is not None else (start_page + max_pages - 1)
    for p in range(start_page, last_page + 1):
        try:
            text = extract_text_from_pdf_page(pdf_path, p)
        except PdfExtractionError:
            break
        combined_parts.append(text)
        combined = "\n".join(combined_parts)
        try:
            mcqs = parse_mcqs_from_text(
                combined, start, end, allow_no_answer=allow_no_answer
            )
            best = mcqs
            if len(best) >= (end - start + 1):
                break
        except McqParsingError:
            # Keep accumulating pages; question/options/answer often spill across pages.
            continue
    combined = "\n".join(combined_parts)
    return best, combined


def _consecutive_runs(missing: list) -> list:
    """Group missing numbers into consecutive runs, e.g. [2, 4, 5, 7] -> [[2], [4, 5], [7]]."""
    if not missing:
        return []
    runs: list = []
    run = [missing[0]]
    for n in missing[1:]:
        if n == run[-1] + 1:
            run.append(n)
        else:
            runs.append(run)
            run = [n]
    runs.append(run)
    return runs


def _fill_missing_from_gaps(
    *,
    combined_text: str,
    current: list,
    start: int,
    end: int,
    allow_no_answer: bool = False,
) -> list:
    """
    Fill missing MCQs by re-parsing only the text between prev and next question.
    We know which numbers are missing; we find their location (between which parsed
    questions they sit) and parse just that segment.
    """
    collected = {m.number: m for m in current}
    missing = [n for n in range(start, end + 1) if n not in collected]
    if not missing:
        return current

    positions = get_question_start_positions(combined_text)
    runs = _consecutive_runs(missing)

    for run in runs:
        prev_num = run[0] - 1
        next_num = run[-1] + 1
        if prev_num not in positions or next_num not in positions:
            continue
        seg_start = positions[prev_num]
        seg_end = positions[next_num]
        segment = combined_text[seg_start:seg_end]
        try:
            mcqs = parse_mcqs_from_text(
                segment, prev_num, next_num, allow_no_answer=allow_no_answer
            )
            for m in mcqs:
                if m.number in run:
                    collected[m.number] = m
        except McqParsingError:
            continue

    return [collected[k] for k in sorted(collected.keys())]


def _fill_missing_mcqs_by_search(
    *,
    pdf_path: str,
    start: int,
    end: int,
    current: list,
    allow_no_answer: bool = False,
    page_min: int | None = None,
    page_max: int | None = None,
) -> list:
    """
    Fill missing MCQs by searching for each question number only within [page_min, page_max].
    This avoids pulling questions from a different section of the PDF (e.g. another chapter).
    """
    collected = {m.number: m for m in current}
    missing = [n for n in range(start, end + 1) if n not in collected]
    for n in missing:
        pages = find_pages_containing_question(
            pdf_path,
            n,
            max_hits=20,
            coarse_step=25,
            require_answer_marker=True,
            page_min=page_min,
            page_max=page_max,
        )
        for p in pages:
            try:
                text = extract_text_from_pdf_page(pdf_path, p)
                mcqs = parse_mcqs_from_text(
                    text, start, end, allow_no_answer=allow_no_answer
                )
                for m in mcqs:
                    collected[m.number] = m
            except (PdfExtractionError, McqParsingError):
                continue
            if n in collected:
                break
    return [collected[k] for k in sorted(collected.keys())]


def _load_config(path: str) -> dict:
    """Load YAML config file; return dict (empty if file missing or invalid)."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a Google Form quiz from a PDF page of MCQs.")
    p.add_argument("--config", default=None, help="Path to YAML config file (CLI args override)")
    p.add_argument("--pdf", default=None, help="Path to the PDF file containing MCQs")
    p.add_argument("--page", type=int, default=None, help="1-indexed page number in the PDF")
    p.add_argument(
        "--end-page",
        type=int,
        default=None,
        dest="end_page",
        help="Last PDF page to read (inclusive). Use so only --page to --end-page are used (e.g. 1088–1116).",
    )
    p.add_argument("--start", type=int, default=None, help="Starting MCQ number (inclusive)")
    p.add_argument("--end", type=int, default=None, help="Ending MCQ number (inclusive)")
    p.add_argument("--title", default=None, help="Google Form title")

    p.add_argument(
        "--classroom_id",
        default=None,
        help="Optional Google Classroom course ID to create an assignment",
    )
    p.add_argument(
        "--credentials",
        default=None,
        help="Path to OAuth client JSON (default: credentials.json)",
    )
    p.add_argument(
        "--token",
        default=None,
        help="Path to cached OAuth token JSON (default: token.json)",
    )
    p.add_argument(
        "--due-date",
        dest="due_date",
        default=None,
        help="Assignment due date YYYY-MM-DD (Classroom only)",
    )
    p.add_argument(
        "--points",
        type=int,
        default=None,
        dest="max_points",
        help="Maximum points for the assignment (Classroom only)",
    )
    p.add_argument(
        "--draft",
        action="store_true",
        help="Create Classroom assignment as draft (Classroom only)",
    )
    p.add_argument(
        "--preview",
        action="store_true",
        help="Parse PDF and print MCQs to stdout; do not create a form or call Google APIs",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="preview",
        help="Alias for --preview",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print which pages were used and parsing progress",
    )
    p.add_argument(
        "--allow-no-answer",
        action="store_true",
        dest="allow_no_answer",
        help="Include questions without ANSWER block (ungraded in the form)",
    )
    p.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="FILE",
        help="Write parsed MCQs to FILE (.json or .md); does not create a form by itself",
    )
    return p


def _apply_config(args: argparse.Namespace) -> None:
    """Merge config file into args; CLI values take precedence."""
    if not args.config:
        return
    cfg = _load_config(args.config)
    if not cfg:
        return
    # Map config keys to arg names (snake_case in YAML)
    key_map = [
        ("pdf", "pdf"),
        ("page", "page"),
        ("end_page", "end_page"),
        ("start", "start"),
        ("end", "end"),
        ("title", "title"),
        ("classroom_id", "classroom_id"),
        ("credentials", "credentials"),
        ("token", "token"),
        ("due_date", "due_date"),
        ("max_points", "max_points"),
        ("points", "max_points"),
        ("draft", "draft"),
        ("allow_no_answer", "allow_no_answer"),
        ("output", "output"),
    ]
    for cfg_key, arg_key in key_map:
        val = cfg.get(cfg_key)
        if val is None:
            continue
        if arg_key in ("draft", "allow_no_answer"):
            setattr(args, arg_key, bool(val))
        elif getattr(args, arg_key, None) is None:
            setattr(args, arg_key, val)
    return


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    _apply_config(args)

    # Resolve required args (from config or CLI)
    for name in ("pdf", "page", "start", "end", "title"):
        if getattr(args, name, None) is None:
            print(
                f"Error: --{name.replace('_', '-')} is required (or set in --config).",
                file=sys.stderr,
            )
            return 2

    # Early validation
    if args.start > args.end:
        print(
            f"Error: --start ({args.start}) must be less than or equal to --end ({args.end}).",
            file=sys.stderr,
        )
        return 2
    if args.page < 1:
        print("Error: --page must be at least 1 (1-indexed).", file=sys.stderr)
        return 2
    end_page = getattr(args, "end_page", None)
    if end_page is not None and end_page < args.page:
        print(
            f"Error: --end-page ({end_page}) must be >= --page ({args.page}).",
            file=sys.stderr,
        )
        return 2

    # Defaults for optional paths
    if args.credentials is None:
        args.credentials = "credentials.json"
    if args.token is None:
        args.token = "token.json"

    verbose = getattr(args, "verbose", False)
    allow_no_answer = getattr(args, "allow_no_answer", False)

    try:
        best_page = None
        if verbose:
            print(f"Extracting text from page {args.page}...", file=sys.stderr)
        text = extract_text_from_pdf_page(args.pdf, args.page)
        try:
            mcqs = parse_mcqs_from_text(
                text, args.start, args.end, allow_no_answer=allow_no_answer
            )
        except McqParsingError:
            # Common real-world issue: the human-visible "page 5" doesn't match the PDF page index.
            # Restrict search to a window around the user-given page so we don't pick content from
            # a different section (e.g. page 451 when user asked for page 1088).
            page_window = 100
            candidates = find_pages_containing_question(
                args.pdf,
                args.start,
                page_min=max(1, args.page - page_window),
                page_max=args.page + page_window,
            )
            best_mcqs = []

            for p in candidates[:10]:
                try:
                    cand_text = extract_text_from_pdf_page(args.pdf, p)
                    cand_mcqs = parse_mcqs_from_text(
                        cand_text, args.start, args.end, allow_no_answer=allow_no_answer
                    )
                    if len(cand_mcqs) > len(best_mcqs):
                        best_page = p
                        best_mcqs = cand_mcqs
                except (PdfExtractionError, McqParsingError):
                    continue

            if best_page is not None and best_page != args.page and best_mcqs:
                msg = (
                    f"Warning: page {args.page} did not parse for range {args.start}-{args.end}. "
                    f"Using detected page {best_page} instead."
                )
                print(msg, file=sys.stderr)
                if verbose:
                    print(f"Using page {best_page} for initial parse.", file=sys.stderr)
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
            if verbose:
                print(
                    f"Collecting MCQs forward from page {start_page} (range {args.start}-{args.end})...",
                    file=sys.stderr,
                )
            mcqs, combined_text = _collect_mcqs_forward(
                pdf_path=args.pdf,
                start_page=start_page,
                start=args.start,
                end=args.end,
                end_page=end_page,
                allow_no_answer=allow_no_answer,
            )
            expected = args.end - args.start + 1
            if len(mcqs) < expected:
                if verbose:
                    missing_count = expected - len(mcqs)
                    print(
                        f"Filling {missing_count} missing question(s) from gap re-parse...",
                        file=sys.stderr,
                    )
                mcqs = _fill_missing_from_gaps(
                    combined_text=combined_text,
                    current=mcqs,
                    start=args.start,
                    end=args.end,
                    allow_no_answer=allow_no_answer,
                )
            if len(mcqs) < expected:
                if verbose:
                    print(
                        f"Searching for {expected - len(mcqs)} missing question(s) by page...",
                        file=sys.stderr,
                    )
                fill_page_max = end_page if end_page is not None else (start_page + 30)
                mcqs = _fill_missing_mcqs_by_search(
                    pdf_path=args.pdf,
                    start=args.start,
                    end=args.end,
                    current=mcqs,
                    allow_no_answer=allow_no_answer,
                    page_min=start_page,
                    page_max=fill_page_max,
                )
            if verbose:
                print(f"Parsed {len(mcqs)} question(s).", file=sys.stderr)
        expected_count = args.end - args.start + 1
        if len(mcqs) != expected_count:
            parsed_nums = [m.number for m in mcqs]
            print(
                f"Warning: parsed {len(mcqs)} question(s) in range {args.start}-{args.end} "
                f"(expected {expected_count}). Parsed numbers: {parsed_nums}",
                file=sys.stderr,
            )
        mcq_dicts = [m.to_dict() for m in mcqs]

        output_path = getattr(args, "output", None)
        if output_path:
            out_path = Path(output_path)
            if out_path.suffix.lower() == ".json":
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(mcq_dicts, f, indent=2, ensure_ascii=False)
            elif out_path.suffix.lower() in (".md", ".markdown"):
                with open(out_path, "w", encoding="utf-8") as f:
                    for m in mcqs:
                        f.write(f"## Question {m.number}\n\n{m.question}\n\n")
                        for i, opt in enumerate(m.options):
                            f.write(f"- {chr(ord('A') + i)}) {opt}\n")
                        if m.answer:
                            f.write(f"\n**Answer:** {m.answer}\n")
                        if m.explanation:
                            f.write(f"\n**Explanation:** {m.explanation}\n")
                        f.write("\n")
            if verbose:
                print(f"Wrote {len(mcqs)} question(s) to {out_path}", file=sys.stderr)

        if getattr(args, "preview", False):
            for m in mcqs:
                print(f"--- Question {m.number} ---")
                print(m.question)
                for i, opt in enumerate(m.options):
                    label = chr(ord("A") + i)
                    print(f"  {label}) {opt}")
                if m.answer:
                    print(f"  Answer: {m.answer}")
                if m.explanation:
                    print(f"  Explanation: {m.explanation}")
                print()
            print(f"Total: {len(mcqs)} question(s) (range {args.start}-{args.end})")
            return 0

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
                due_date=getattr(args, "due_date", None),
                max_points=getattr(args, "max_points", None),
                draft=getattr(args, "draft", False),
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

