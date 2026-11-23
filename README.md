# HEAsyn

Literature collection, embedding screening, and PDF-based POP extraction.

## Structure

```text
heasyn/retrieval/   Literature search, deduplication, embedding ranking, PDF download
heasyn/extraction/  PDF parsing, POP prompts, model clients, JSON validation
heasyn/config.py    Model defaults and alternatives
dashboard.py       Local ranking server
web/               Ranking interface
data/              Paper abstracts and saved rankings
tools/             Dataset preparation and command-line ranking
tests/             Pipeline and interface tests
```

## Installation

Python 3.11 or newer. Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Literature Collection and Screening

```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "YOUR_SEMANTIC_SCHOLAR_API_KEY"
.\.venv\Scripts\python.exe -m heasyn collect --search-query "high entropy alloy oxygen reduction" --query "Pt based high entropy alloy electrocatalyst oxygen reduction reaction mass activity" --max-papers 100 --top-k 20 --output outputs/collection
```

The Semantic Scholar key is optional. Use `--embedding-model` to change the
embedding model and `--min-score` to set a cosine threshold. The default is
`sentence-transformers/all-mpnet-base-v2`.

Outputs include candidate records, ranked records, selected papers, and available
open-access PDFs.

## PDF Parsing and POP

```powershell
$env:OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider openai --model gpt-4o --output outputs/pop
```

Additional providers:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_API_KEY"
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider anthropic --model claude-sonnet-4-6
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider ollama --model qwen2.5:7b
```

The seven steps are Problem, Catalyst, Composition, Performance, ParticleSize,
SynthesisFactor, and Relationships. Prompts are in `heasyn/extraction/prompts.py`.
The parser reads PDF text; scanned PDFs require OCR before processing.

Credentials are read from environment variables. `.env.example` lists the
variables and is not loaded automatically. Model alternatives are listed in
`heasyn/config.py`. Hosted providers receive the extracted text.

Use `all` to run collection and extraction together, or `--help` for all options.

## Embedding Workbench

```powershell
.\.venv\Scripts\python.exe dashboard.py --port 8765
```

Open http://127.0.0.1:8765 to rank papers, view abstracts and category distributions,
and export CSV or JSON. The default workbench model is
`sentence-transformers/all-MiniLM-L6-v2`. Models download on first use and are
cached in `.cache/`. Saved and newly computed results are labelled in the interface.

The included dataset contains 80 paper records across four categories.
Custom JSON datasets must contain a list of papers, or an object with a `papers`
list. Each paper requires `paper_id`, `title`, and `abstract`; optional fields are
`category`, `year`, `doi`, `url`, and `source_file`.

```powershell
.\.venv\Scripts\python.exe dashboard.py --dataset path/to/papers.json
.\.venv\Scripts\python.exe tools/rank_sample.py --top-k 20 --output outputs/ranking.json
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m heasyn self-test
```

External API calls are mocked in the tests. Browser tests are in
`tests/browser_smoke.cjs` and require Playwright and a running workbench.
