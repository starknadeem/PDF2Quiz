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
  requirements.txt
  README.md
```

## Installation

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

Basic: create a Google Form quiz from a PDF page and question range:

```bash
python3 generate_quiz.py --pdf mcqs.pdf --page 5 --start 21 --end 30 --title "Quiz 1"
```

Example (your PDF style): start at page 9 and generate questions 1–6:

```bash
python3 generate_quiz.py --pdf mcqs.pdf --page 9 --start 1 --end 6 --title "Quiz 1-6"
```

Optional: also create a Classroom assignment in a course:

```bash
python3 generate_quiz.py \
  --pdf mcqs.pdf --page 5 --start 21 --end 30 --title "Quiz 1" \
  --classroom_id "123456789012"
```

You can also set custom OAuth file paths:

```bash
python3 generate_quiz.py \
  --pdf mcqs.pdf --page 5 --start 21 --end 30 --title "Quiz 1" \
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

If Classroom upload is used:

- `Quiz assignment created successfully.`

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

