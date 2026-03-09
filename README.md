# PDF → Google Form Quiz Generator (CLI)

This project provides a Python CLI tool for teachers that:

- Extracts MCQs from a specific **PDF page**
- Parses a specified **question number range** (even if questions span multiple PDF pages)
- Creates a **Google Form** configured as a **graded quiz**
- Optionally creates a **Google Classroom assignment** that links to the generated form

## Project structure

```
project/
  generate_quiz.py
  pdf_parser.py
  form_creator.py
  classroom_uploader.py
  auth.py
  requirements.txt
  requirements-dev.txt
  tests/
    test_pdf_parser.py
    test_form_creator.py
    test_generate_quiz.py
  README.md
```

## Installation

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

To run tests (optional; install dev dependencies first):

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Google API setup (OAuth)

You must create OAuth credentials and download a client JSON file.

1. In Google Cloud Console, create or select a project.
2. Enable APIs:
   - **Google Forms API**
   - **Google Classroom API** (only needed if using `--classroom_id`)
3. Configure OAuth consent screen (External is fine for personal use).
4. Create OAuth Client ID:
   - Application type: **Desktop app**
5. Download the JSON file and save it as `credentials.json` in this folder (or pass `--credentials`).

On first run, your browser will open to complete OAuth login. A `token.json` file will be created for reuse.

## Usage

Basic: create a Google Form quiz from a PDF start/end page range and question range:

```bash
python3 generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1"
```

Example (your PDF style): read pages 9-11 and generate questions 1-6:

```bash
python3 generate_quiz.py --pdf mcqs.pdf --page 9 --end-page 11 --start 1 --end 6 --title "Quiz 1-6"
```

Optional: also create a Classroom assignment in a course:

```bash
python3 generate_quiz.py \
  --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" \
  --classroom_id "123456789012"
```

`--classroom_id` accepts either:
- numeric course ID (recommended): `123456789012`
- Classroom URL-style base64 ID: `ODUwMTUwNDcxNDI5` (auto-decoded by the tool)

Preview parsed MCQs without creating a form or calling Google APIs:

```bash
python3 generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --preview
```

If some questions are still missing after automatic parsing, the CLI now asks for manual page hints before creating the form. Example input:

```text
4=1090, 7=1092
```

This means "question 4 is on page 1090" and "question 7 is on page 1092". The tool re-parses those pages (and nearby spillover) to recover missing MCQs.

Use `--page` as the start page and `--end-page` as the end page (inclusive).

**Config file:** You can put options in a YAML file and pass `--config quiz_config.yaml`. CLI arguments override config values. Example `quiz_config.yaml`:

```yaml
pdf: mcqs.pdf
page: 5
end_page: 8
start: 21
end: 30
title: "Quiz 1"
classroom_id: "123456789012"
credentials: credentials.json
token: token.json
due_date: "2025-03-15"
points: 10
draft: false
```

Then run: `python3 generate_quiz.py --config quiz_config.yaml` (override any value with CLI, e.g. `--title "Quiz 2"`).

**Classroom options:** Use `--due-date 2025-03-15`, `--points 10`, and `--draft` to set assignment due date, max points, or create as draft.

**Export and ungraded questions:** Use `--output parsed.json` or `--output parsed.md` to write parsed MCQs to a file (in addition to creating the form). Use `--allow-no-answer` to include questions that have no ANSWER block in the PDF (they appear in the form as ungraded).

You can also set custom OAuth file paths:

```bash
python3 generate_quiz.py \
  --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" \
  --credentials path/to/credentials.json --token path/to/token.json
```

## PDF format expectations

The parser expects MCQs roughly like:

```
21. What is the capital of France?
    A) Berlin
    B) Madrid
    C) Paris
    D) Rome
```

It also supports common variants like `21)` and `Q-21` / `Q21`, and options like `A.` / `b)` and questions with **1–4+ options**.

### Answer + explanation support (for scoring)

If your PDF includes sections like:

```
ANSWER:
<correct option text or letter>
EXPLANATION:
<explanation text...>
```

Then the generated Google Form quiz will set:

- an **answer key** (so Google Forms can grade automatically)
- **feedback** (the explanation is shown as feedback)

### Watermark links

Common watermark links (for example `t.me/...` or `https://...`) are automatically removed, even if they appear inline at the end of a question or option.

If the PDF text extraction is empty (common for scanned PDFs), you’ll need OCR before running this tool.

## Output

On success:

- `Form created successfully`
- `Form URL: <link>`

If questions remain missing and you do not confirm continuation, form creation is aborted to avoid unreliable/incomplete quizzes.

If Classroom upload is used:

- `Quiz assignment created successfully.`

**Exit codes:** `0` = success; `1` = unexpected error; `2` = PDF or parsing error (invalid path, page, range, or format); `3` = Google API error (OAuth or Forms/Classroom). Use `--verbose` / `-v` to print which page(s) were used and parsing progress.

## Troubleshooting

- **Page out of range**: check `--page` is 1-indexed and within the PDF page count.
- **No extractable text**: the page is likely scanned; run OCR first.
- **Parsing failures**: MCQ formatting may differ (option labels, numbering, wrapped lines).
- **Google API errors**: verify APIs are enabled, OAuth consent screen is configured, and your Google account has access to the target Classroom course.

## Pushing to GitHub (important)

Do **not** commit these files (they contain secrets/tokens):

- `token.json`
- `credentials.json`
- `.venv/`

Make sure your `.gitignore` includes them before pushing.

