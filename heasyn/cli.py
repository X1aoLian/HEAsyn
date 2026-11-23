from __future__ import annotations
import argparse
import logging
from pathlib import Path
from .common import save_json
from .config import DEFAULT_MODELS, DEFAULT_EMBEDDING
from .retrieval.collection import run_collection
from .extraction.client import LLMClient
from .extraction.pop import run_extraction

LOG = logging.getLogger("heasyn")

def main(argv=None):
    parser = argparse.ArgumentParser(description='HEAsyn literature screening and POP extraction', formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["all", "collect", "pop", "self-test"])
    parser.add_argument("--query", default="Pt-based high entropy alloy oxygen reduction reaction mass activity")
    parser.add_argument("--search-query", action="append", help="Database query; repeat to combine searches. --query is used for embedding screening.")
    parser.add_argument("--max-papers", type=int, default=100, help="Maximum search results per query (1-1000).")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-score", type=float, help="Optional cosine cutoff; calibrate separately for each embedding model.")
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING)
    parser.add_argument("--device", default=None, help="cpu, cuda, or automatic if omitted")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--query-prefix", default=None)
    parser.add_argument("--document-prefix", default=None)
    parser.add_argument("--pdf-dir", type=Path, help="Local PDFs; all PDFs are processed in pop mode.")
    parser.add_argument("--output", type=Path, default=Path("heasyn_output"))
    parser.add_argument("--provider", choices=list(DEFAULT_MODELS), default="openai")
    parser.add_argument("--model", help="POP model; defaults depend on --provider.")
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL, including /v1; unused for Anthropic.")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama server root URL.")
    parser.add_argument("--ollama-context-tokens", type=int, default=32768,
                        help="Context size supported by your local model; subject to a conservative input guard.")
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--max-prompt-chars", type=int, default=120000,
                        help="Character guard, not a token count; must fit the chosen model's context window.")
    args = parser.parse_args(argv)
    if args.mode == "self-test":
        import unittest
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / 'tests'))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if not 1 <= args.max_papers <= 1000 or args.top_k < 1 or args.batch_size < 1:
        parser.error("Require 1 <= max-papers <= 1000, top-k >= 1, and batch-size >= 1.")
    if args.min_score is not None and not -1 <= args.min_score <= 1:
        parser.error("min-score must lie in [-1, 1].")
    if args.max_output_tokens < 1 or args.max_prompt_chars < 1:
        parser.error("Token and character limits must be positive.")
    if args.ollama_context_tokens <= args.max_output_tokens:
        parser.error("ollama-context-tokens must exceed max-output-tokens.")
    if args.mode == "pop" and (args.pdf_dir is None or not args.pdf_dir.is_dir()):
        parser.error("pop mode requires an existing --pdf-dir.")
    if args.mode != "collect":
        LLMClient(args)  # Validate credentials before expensive retrieval/embedding.
    args.output.mkdir(parents=True, exist_ok=True)
    # Record only non-secret configuration. Custom URLs may contain credentials.
    config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items() if key not in {"base_url", "ollama_url"}}
    config["model"] = args.model or DEFAULT_MODELS[args.provider]
    save_json(args.output / "run_config.json", config)
    if args.mode in {"all", "collect"}:
        records = run_collection(args, args.output)
    else:
        records = [{"pdf_path": str(p.resolve()), "title": p.stem} for p in sorted(args.pdf_dir.rglob("*"))
                   if p.is_file() and p.suffix.lower() == ".pdf"]
    if args.mode == "collect":
        return 0 if records else 1
    if not records:
        LOG.error("No papers are available for POP extraction.")
        return 1
    manifest = run_extraction(records, args, args.output)
    return 0 if all(row["status"] in {"complete", "no_target_catalyst"} for row in manifest) else 1
