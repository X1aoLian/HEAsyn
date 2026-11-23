"""Compute an embedding ranking for the bundled dataset or a custom dataset."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
sys.path.insert(0, str(ROOT))
from heasyn.common import save_json
from heasyn.retrieval.dataset import load_dataset, DEFAULT_QUERY
from heasyn.retrieval.embedding import rank_dataset

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/papers_sample.json")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/ranking.json")
    args = parser.parse_args()
    result = rank_dataset(load_dataset(args.dataset), args.query, args.model, args.top_k, cache_dir=ROOT / ".cache/embeddings")
    save_json(args.output, result)
    for row in result["ranking"][:args.top_k]:
        print(f"{row['rank']:>3}  {row['similarity']:.4f}  {row['title']}")
    print(f"Saved {args.output}")
