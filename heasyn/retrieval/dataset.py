"""Validated local datasets shared by the CLI and ranking workbench."""
import hashlib
import json
from pathlib import Path

CATEGORIES = {
    "expert_curated": "Expert-curated target papers",
    "keyword_retrieved": "Keyword-retrieved domain papers",
    "adjacent_domain": "Adjacent-domain papers",
    "out_of_domain": "Out-of-domain papers",
}
DEFAULT_QUERY = "Pt based high entropy alloy electrocatalyst oxygen reduction reaction mass activity"
BROAD_QUERY = "High entropy alloy synthesis characterization"


def load_dataset(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    papers = data.get("papers") if isinstance(data, dict) else data
    if not isinstance(papers, list) or not papers:
        raise ValueError("Dataset must contain a nonempty papers list.")
    seen = set()
    for paper in papers:
        if not isinstance(paper, dict):
            raise ValueError("Every paper must be an object.")
        for key in ("paper_id", "title", "abstract"):
            if not isinstance(paper.get(key), str) or not paper[key].strip():
                raise ValueError(f"Every paper needs a nonempty {key}.")
        if paper["paper_id"] in seen:
            raise ValueError("Dataset contains duplicate paper IDs.")
        seen.add(paper["paper_id"])
    return papers


def dataset_digest(papers):
    return hashlib.sha256(json.dumps(papers, ensure_ascii=True, sort_keys=True).encode()).hexdigest()
