"""Build a deterministic abstract dataset from the existing research corpus.

Usage: python tools/build_sample_dataset.py --source D:/MyCode/LLM-Catalyst
No PDFs, API keys, machine-specific paths, or personal settings are copied.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


def clean(text):
    text = re.sub(r"_x[0-9a-fA-F]{4}_", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def build(source, per_category=20):
    if per_category < 1:
        raise ValueError("per_category must be positive.")
    root = source / "RAG" / "downloaded_papers"
    groups = {}
    with (source / "data" / "final_dataset.csv").open(encoding="utf-8-sig", newline="") as handle:
        groups["expert_curated"] = [dict(row, source_file="data/final_dataset.csv")
                                    for row in csv.DictReader(handle) if row["label"] == "0"]
    for category, filename in [("keyword_retrieved", "original_metadata.json"),
                               ("adjacent_domain", "related_metadata.json"),
                               ("out_of_domain", "unrelated_metadata.json")]:
        content = json.loads((root / filename).read_text(encoding="utf-8-sig"))
        groups[category] = [dict(item.get("paper", item), source_file=filename) for item in content["papers"]]
    papers, seen = [], set()
    for category, rows in groups.items():
        count = 0
        for row in rows:
            title, abstract = clean(row.get("title")), clean(row.get("abstract"))
            identity = re.sub(r"\W+", "", title.casefold())
            if not title or len(abstract) < 100 or identity in seen:
                continue
            seen.add(identity)
            doi = (row.get("externalIds") or {}).get("DOI") or row.get("doi")
            papers.append({"paper_id": row.get("paperId") or hashlib.sha256(identity.encode()).hexdigest()[:20],
                           "title": title, "abstract": abstract, "category": category,
                           "year": row.get("year"), "doi": doi,
                           "url": row.get("url") or ("https://doi.org/" + doi if doi else None),
                           "source_file": row["source_file"]})
            count += 1
            if count == per_category:
                break
    return {"name": "HEAsyn abstract screening sample", "version": 1,
            "provenance": "Selected from the existing LLM-Catalyst research corpus; original abstracts are preserved with whitespace/control-code cleanup.",
            "category_note": "Labels describe collection sources, not independently adjudicated relevance or paper quality.",
            "sampling": f"First {per_category} unique nonempty abstracts per source category; deterministic, not random.",
            "purpose": "Local demonstration and software testing; not the manuscript evaluation benchmark.",
            "papers": papers}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--per-category", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "papers_sample.json")
    args = parser.parse_args()
    dataset = build(args.source, args.per_category)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, ensure_ascii=True, indent=2), encoding="utf-8")
    from collections import Counter
    print(dict(Counter(p["category"] for p in dataset["papers"])))
