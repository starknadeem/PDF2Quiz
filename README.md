# PDF to Google Form Quiz Generator (CLI)

Generate graded Google Form quizzes from MCQs in a PDF, and optionally post them to Google Classroom.

## What this tool does

- Extracts text from PDF pages.
- Parses MCQs in a given question range.
- Creates a Google Form quiz with answer key + feedback (when available).
- Optionally creates a Google Classroom assignment with the generated Form link.
- Prompts you when questions are missing before creating an incomplete form.

## Project files

```text
project/
  generate_quiz.py
  pdf_parser.py
  form_creator.py
  classroom_uploader.py
  auth.py
  requirements.txt
  requirements-dev.txt
  tests/
    test_auth.py
    test_classroom_uploader.py
    test_form_creator.py
    test_generate_quiz.py
    test_pdf_parser.py
  README.md
```

## Prerequisites

- Python 3.10+ recommended
- Google Cloud project with OAuth client
- APIs enabled:
  - Google Forms API
  - Google Classroom API (only if you use `--classroom_id`)

## Setup (Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run tests (optional):

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Setup (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run tests (optional):

```powershell
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Google OAuth setup (one-time)

1. Open Google Cloud Console and create/select a project.
2. Enable APIs:
   - Google Forms API
   - Google Classroom API (if needed)
3. Configure OAuth consent screen.
4. Create OAuth Client ID:
   - App type: Desktop app
5. Download the client JSON and save it as `credentials.json` in project root.

On first run, browser auth opens and `token.json` is created automatically.

## Quick start commands

### 1) Create form quiz from PDF

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1"
```

### 2) Preview only (no Google API calls)

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --preview
```

### 3) Create form + Classroom assignment

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --classroom_id "123456789012"
```

### 4) Classroom assignment as draft

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --classroom_id "123456789012" --draft
```

### 5) Classroom assignment with due date and points

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --classroom_id "123456789012" --due-date 2026-03-15 --points 10
```

### 6) Save parsed output to file

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --output parsed.json
```

or:

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --output parsed.md
```

### 7) Allow ungraded questions (no ANSWER block)

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --allow-no-answer
```

### 8) Use custom credentials/token paths

```bash
python generate_quiz.py --pdf mcqs.pdf --page 5 --end-page 8 --start 21 --end 30 --title "Quiz 1" --credentials path/to/credentials.json --token path/to/token.json
```

## Classroom ID format

`--classroom_id` accepts both:

- Numeric course ID: `123456789012` (recommended)
- URL-style base64 ID: `ODUwMTUwNDcxNDI5` (auto-decoded by tool)

## Missing question recovery flow

If parser misses question(s), CLI asks for manual page hints before creating form:

```text
Missing questions: [4, 7]
Enter page mappings as question=page (e.g. 4=1090, 7=1092), or press Enter to skip:
4=1090, 7=1092
```

Tool re-parses those pages (and nearby spillover) to recover missing MCQs.

## Config file mode

You can keep options in YAML:

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
due_date: "2026-03-15"
points: 10
draft: false
allow_no_answer: false
output: parsed.json
```

Run with:

```bash
python generate_quiz.py --config quiz_config.yaml
```

CLI flags override config values.

## Full CLI options reference

```text
--config
--pdf
--page
--end-page
--start
--end
--title
--classroom_id
--credentials
--token
--due-date
--points
--draft
--preview / --dry-run
--verbose / -v
--allow-no-answer
--output / -o
```

## Expected PDF format

Example:

```text
21. What is the capital of France?
    A) Berlin
    B) Madrid
    C) Paris
    D) Rome
ANSWER:
C
EXPLANATION:
Paris is the capital of France.
```

Supported variants include `21)`, `Q-21`, `Q21`, option styles like `A)` / `A.` / `(A)`, and wrapped option lines.

## Output and exit codes

Success output:

- `Form created successfully`
- `Form URL: <link>`
- `Quiz assignment created successfully.` (when Classroom is enabled)

Exit codes:

- `0` success
- `1` unexpected error
- `2` PDF/parsing/validation error
- `3` Google API error (OAuth/Forms/Classroom)

## Troubleshooting

- **No text extracted**: PDF may be scanned; run OCR first.
- **Questions missing**: run with `--preview -v` and provide page hints when prompted.
- **Classroom 404**: account has no access to that course, or course does not exist.
- **OAuth issues**: ensure APIs enabled and consent screen configured.

## Security / Git notes

Do not commit:

- `token.json`
- `credentials.json`
- `.venv/`

Ensure these are in `.gitignore`.

