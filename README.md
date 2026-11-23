# HEAsyn Data Engine

Two independent stages implement literature collection and embedding screening,
followed by text-based PDF parsing and seven-step POP extraction. A local workbench
displays real embedding rankings for a bundled paper-abstract sample.

## Layout

```text
heasyn/
  retrieval/       # Part 1: database search, deduplication, embeddings, PDF download
  extraction/      # Part 2: PDF text, manuscript-based POP prompts, LLM clients
  config.py        # Model defaults and commented model alternatives
  common.py        # Credential handling, HTTP retries, atomic JSON output
  cli.py           # collect / pop / all / self-test commands
dashboard.py       # Local ranking API and web server
web/               # Ranking interface: HTML, CSS, JavaScript
data/              # 80 real paper records and saved real embedding runs
tools/             # Rebuild the sample or compute rankings without the UI
tests/             # Offline regression tests (no paid API calls)
heasyn_pipeline.py # Compatibility entry point
```

## Setup

Python 3.11 or newer is recommended. From this `code` directory, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use a CPU or CUDA PyTorch build appropriate to your machine. No credentials are
needed for the bundled ranking demo. Models download from Hugging Face on first
use. The browser does not send paper text to an LLM; embedding inference is local.

## Ranking Workbench

```powershell
.\.venv\Scripts\python.exe dashboard.py --port 8765
```

Open http://127.0.0.1:8765. Choose a query, model, Top K, and optional cosine cutoff,
then run the ranking. The table includes the full ranking and marks the selected
subset. Category/search filters affect the visible table; CSV exports those rows,
while JSON exports the entire run. The detail panel contains the source abstract.

The initial view is a **saved real model run**, explicitly labelled with its model,
date, and dataset hash. New requests compute real sentence-transformer embeddings;
there is no keyword-based or random fallback. MiniLM is the lightweight demo model;
MPNet is the pipeline default. Model scores are not probabilities and should not be
compared across models as if they shared a calibrated scale.

The server binds only to loopback, serves an explicit static-file allowlist, and
rejects cross-origin ranking requests. It is a local development tool, not a
multi-user production service. No API credentials are exposed in its interface.

Document vectors and models are cached in `.cache/`. Cache keys include dataset
content and model name. Delete the embedding cache when changing model revisions.
Tokenizer truncation is reported in each ranking. Saved runs use abstract text only,
normalized dense vectors, cosine similarity, and deterministic ID tie-breaking.

Custom dataset:

```powershell
.\.venv\Scripts\python.exe dashboard.py --dataset path/to/papers.json --port 8766
.\.venv\Scripts\python.exe tools/rank_sample.py --top-k 20 --output outputs/ranking.json
```

A dataset is a JSON list, or an object containing `papers`. Each record requires
unique `paper_id`, `title`, and `abstract` strings. Optional fields: `category`,
`year`, `doi`, `url`, `source_file`. A saved ranking is used only when its dataset
hash matches; custom datasets otherwise start without results.

## Part 1: Collection and Embedding Screening

```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "YOUR_SEMANTIC_SCHOLAR_API_KEY"
.\.venv\Scripts\python.exe -m heasyn collect --search-query "high entropy alloy oxygen reduction" --query "Pt based high entropy alloy electrocatalyst oxygen reduction reaction mass activity" --max-papers 100 --top-k 20 --output outputs/collection
```

The Semantic Scholar key is optional but recommended for rate limits. Search
queries may be repeated. The pipeline paginates search results, deduplicates IDs,
DOIs and titles, excludes missing abstracts from embedding screening, ranks the
remaining abstracts, and downloads selected open-access PDFs when available.
An inaccessible PDF is recorded as unavailable, not treated as a successful parse.
Local files can be supplied using `--pdf-dir` and Semantic Scholar IDs as filenames.

Outputs include `candidates.json`, `ranked_papers.json`, `ranked_papers.csv`,
`selected_papers.json`, and `pdfs/`. Database coverage, abstract availability and
query selection affect the result; this is not an exhaustive literature census.

## Part 2: PDF Parsing and POP

```powershell
$env:OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider openai --model gpt-4o --output outputs/pop
```

Alternative providers:

```powershell
$env:ANTHROPIC_API_KEY = "YOUR_ANTHROPIC_API_KEY"
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider anthropic --model claude-sonnet-4-6
.\.venv\Scripts\python.exe -m heasyn pop --pdf-dir path/to/pdfs --provider ollama --model qwen2.5:7b
```

Model availability depends on the account or local installation. Additional
choices and instruction prefixes are documented in `heasyn/config.py` and
`heasyn/retrieval/embedding.py`. Keys are read from environment variables only;
`.env.example` is a placeholder reference, not an automatically loaded file.
Hosted POP providers receive the extracted PDF text. Confirm permission before
sending unpublished or confidential papers. API use may incur charges.

The prompt sequence in `heasyn/extraction/prompts.py` follows the manuscript's
appendix: **Problem -> Catalyst -> Composition -> Performance -> ParticleSize ->
SynthesisFactor -> Relationships**. Earlier entities are supplied where required.
Prompts are adapted into executable JSON contracts rather than copied verbatim:
example measurements are replaced by placeholders, missing data is `Not reported`,
and computational evidence is distinguished from experimental evidence.

Every stage validates JSON structure and retries one malformed response. Raw
answers, partial outputs, page-marked text, PDF hashes and provenance are retained.
No target catalyst stops extraction after the Catalyst stage. Failures remain
explicit in the manifest. Scientific correctness still requires expert review;
schema validation is not evidence verification.

The parser extracts text only: no OCR, figure interpretation or layout-aware table
reconstruction. Very short text is rejected; blank pages are flagged. Full paper
text is not silently shortened to fit the LLM. Character limits are guards, not
exact token estimates; choose a suitable context window. Ollama also uses a
conservative byte-based input/output guard and an explicit context setting.

Use `all` instead of `collect` or `pop` to connect both parts. `--help` lists all
parameters. Real API keys are intentionally not included.

## Sample Provenance

`data/papers_sample.json` contains 80 unique records: 20 per source group
(`expert_curated`, `keyword_retrieved`, `adjacent_domain`, `out_of_domain`). They were
imported deterministically from the existing LLM-Catalyst archive: its
`data/final_dataset.csv` and three `RAG/downloaded_papers/*_metadata.json` files.
Source filename, available DOI/URL, title and abstract are retained. The importer
cleans whitespace and spreadsheet escape sequences and excludes short abstracts.

These are real archived paper records, not generated scientific claims. Their
metadata has not been independently reverified. Source categories are not a gold
standard of query relevance, and the sample is **not the manuscript benchmark**.
Full PDFs are not redistributed. Abstracts retain their original rights; review
source licences before publishing or redistributing this sample.

`tools/build_sample_dataset.py --help` describes rebuilding from the original
archive. The original archive is not needed to use the bundled dataset.

## Verification

```powershell
.\.venv\Scripts\python.exe -m heasyn self-test
```

Tests cover collection pagination, deduplication, PDF validation/parsing, ranking,
embedding-cache reuse, truncation reporting, POP dependencies, response schemas,
retry behavior, provider payloads, request validation and the local HTTP API.
They use mocks for external services. Live LLM extraction and database access need
separate verification with authorized credentials. Saved demo rankings were
computed using the real MiniLM model, not the test encoder.

An optional `tests/browser_smoke.cjs` script exercises the running workbench with
Playwright: live inference, category/search filtering, selection, CSV download,
empty results, nonblank chart pixels, and desktop/mobile layouts. Install
Playwright separately to run it with Node.js. `WORKBENCH_URL` overrides the local
URL and `BROWSER_EXECUTABLE` can specify an installed browser. Screenshots are
written under `.cache/browser/` and are not part of the paper dataset.
