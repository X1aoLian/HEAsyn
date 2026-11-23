from __future__ import annotations
import logging
from pathlib import Path
import time
import hashlib
from functools import lru_cache

LOG = logging.getLogger("heasyn")

def embedding_prefixes(model_name):
    name = model_name.lower()
    task = "Given a scientific query, retrieve relevant paper abstracts"
    if "qwen3-embedding" in name or "e5-large-instruct" in name:
        return f"Instruct: {task}\nQuery: ", ""
    if "llama-embed-nemotron" in name:
        return "Instruct: Given a scientific paper title and abstract, retrieve relevant papers on the same topic\nQuery: ", ""
    if "nomic" in name:
        return "search_query: ", "search_document: "
    if "e5" in name:
        return "query: ", "passage: "
    if "bge" in name:
        return "Represent this sentence for searching relevant passages: ", ""
    return "", ""


def select_ranked(papers, scores, top_k, min_score):
    ranked = sorted((dict(p, similarity=float(s)) for p, s in zip(papers, scores)),
                    key=lambda p: (-p["similarity"], p["paper_id"]))
    selected = [p for p in ranked if min_score is None or p["similarity"] >= min_score][:top_k]
    return ranked, selected


def screen_papers(papers, args):
    eligible = [p for p in papers if p["abstract"].strip()]
    LOG.info("Screening %d abstracts; %d records lack abstracts.", len(eligible), len(papers) - len(eligible))
    if not eligible:
        return [], []
    model = load_encoder(args.embedding_model, args.device, args.trust_remote_code)
    qp, dp = embedding_prefixes(args.embedding_model)
    qp = qp if args.query_prefix is None else args.query_prefix
    dp = dp if args.document_prefix is None else args.document_prefix
    # Explicit empty prompts prevent saved model defaults from being applied twice.
    options = dict(convert_to_numpy=True, normalize_embeddings=True, batch_size=args.batch_size)
    documents = model.encode_document([p["abstract"] for p in eligible], prompt=dp, **options)
    query = model.encode_query([args.query], prompt=qp, **options)[0]
    return select_ranked(eligible, documents @ query, args.top_k, args.min_score)


@lru_cache(maxsize=2)
def load_encoder(model_name, device=None, trust_remote_code=False):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, device=device, trust_remote_code=trust_remote_code)


def rank_dataset(papers, query, model_name, top_k=20, min_score=None, cache_dir=None, device="cpu"):
    """Rank abstracts by embedding cosine similarity; cache by content and model."""
    import numpy as np
    from collections import Counter
    from datetime import datetime, timezone
    from .dataset import dataset_digest
    if not query.strip() or not 1 <= top_k <= len(papers):
        raise ValueError("Query must be nonempty and top_k must be within the dataset size.")
    if min_score is not None and not -1 <= min_score <= 1:
        raise ValueError("min_score must be in [-1, 1].")
    started = time.perf_counter()
    encoder = load_encoder(model_name, device)
    qp, dp = embedding_prefixes(model_name)
    digest = dataset_digest(papers)
    cache_key = hashlib.sha256((digest + model_name + dp).encode()).hexdigest()
    cache = Path(cache_dir) / (cache_key + ".npz") if cache_dir else None
    options = dict(convert_to_numpy=True, normalize_embeddings=True, batch_size=8, show_progress_bar=False)
    if cache and cache.exists():
        with np.load(cache, allow_pickle=False) as stored:
            matrix = stored["embeddings"]
    else:
        matrix = encoder.encode_document([p["abstract"] for p in papers], prompt=dp, **options)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache, embeddings=matrix)
    vector = encoder.encode_query([query], prompt=qp, **options)[0]
    if matrix.shape != (len(papers), len(vector)) or not np.isfinite(matrix).all() or not np.isfinite(vector).all():
        raise ValueError("Invalid embedding matrix; remove the document cache and retry.")
    ranked, selected = select_ranked(papers, np.clip(matrix @ vector, -1, 1), top_k, min_score)
    for index, paper in enumerate(ranked, 1):
        paper["rank"] = index
    selected_ids = {p["paper_id"] for p in selected}
    selected = [p for p in ranked if p["paper_id"] in selected_ids]
    counts = Counter(p.get("category", "unlabelled") for p in selected)
    # Report tokenizer truncation rather than presenting a shortened input as full text.
    lengths = encoder.tokenizer([dp + p["abstract"] for p in papers], truncation=False, add_special_tokens=True, verbose=False)["input_ids"]
    truncated = sum(len(tokens) > encoder.max_seq_length for tokens in lengths)
    return {"query": query, "model": model_name, "dataset_sha256": digest,
            "created_at": datetime.now(timezone.utc).isoformat(), "total": len(papers),
            "top_k": top_k, "min_score": min_score, "selected_count": len(selected),
            "category_counts": dict(counts), "ranking": ranked,
            "selected_ids": [p["paper_id"] for p in selected], "truncated_abstracts": truncated,
            "model_max_tokens": encoder.max_seq_length,
            "elapsed_seconds": round(time.perf_counter() - started, 3)}
