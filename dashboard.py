"""Local-only embedding ranking workbench. Run with python dashboard.py."""
from __future__ import annotations

import argparse
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))

from heasyn.retrieval.dataset import BROAD_QUERY, CATEGORIES, DEFAULT_QUERY, dataset_digest, load_dataset
from heasyn.retrieval.embedding import rank_dataset

MODELS = ["sentence-transformers/all-MiniLM-L6-v2", "sentence-transformers/all-mpnet-base-v2"]
LOG = logging.getLogger("heasyn.dashboard")


def validate_request(payload, size):
    if not isinstance(payload, dict):
        raise ValueError("Request must be a JSON object.")
    query = payload.get("query")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
        raise ValueError("Query must contain 1 to 2000 characters.")
    model = payload.get("model", MODELS[0])
    if model not in MODELS:
        raise ValueError("Select a supported embedding model.")
    top_k = payload.get("top_k", 20)
    if type(top_k) is not int or not 1 <= top_k <= size:
        raise ValueError(f"Top K must be an integer between 1 and {size}.")
    cutoff = payload.get("min_score")
    if cutoff is not None and (type(cutoff) not in (float, int) or not -1 <= cutoff <= 1):
        raise ValueError("Minimum similarity must be a number between -1 and 1.")
    return query.strip(), model, top_k, cutoff


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, dataset):
        self.papers = load_dataset(dataset)
        self.digest = dataset_digest(self.papers)
        self.inference_lock = threading.Lock()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=True).encode(), "application/json; charset=utf-8")

    def valid_host(self):
        return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def do_GET(self):
        if not self.valid_host():
            return self.send_json(403, {"error": "Local requests only."})
        path = urlsplit(self.path).path
        if path == "/api/config":
            return self.send_json(200, {"categories": CATEGORIES, "models": MODELS,
                "queries": {"precise": DEFAULT_QUERY, "broad": BROAD_QUERY},
                "total": len(self.server.papers), "dataset_sha256": self.server.digest,
                "counts": dict(Counter(p.get("category", "unlabelled") for p in self.server.papers))})
        if path in {"/api/snapshot/precise", "/api/snapshot/broad"}:
            snapshot = ROOT / "data/demo_rankings" / (path.rsplit("/", 1)[1] + ".json")
            if snapshot.exists():
                result = json.loads(snapshot.read_text(encoding="utf-8"))
                if result["dataset_sha256"] == self.server.digest:
                    return self.send_json(200, dict(result, result_source="saved"))
            return self.send_json(404, {"error": "No matching saved ranking. Run a new ranking."})
        files = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if path not in files:
            return self.send_json(404, {"error": "Not found."})
        file = ROOT / "web" / files[path]
        kind = mimetypes.guess_type(file)[0] or "application/octet-stream"
        self.send_bytes(200, file.read_bytes(), kind + "; charset=utf-8")

    def do_POST(self):
        expected = {f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}"}
        if not self.valid_host() or self.headers.get("Origin", "") not in expected | {""}:
            return self.send_json(403, {"error": "Local requests only."})
        if self.path != "/api/rank":
            return self.send_json(404, {"error": "Not found."})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 1 <= length <= 16384:
                raise ValueError("Invalid request size.")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Content-Type must be application/json.")
            payload = json.loads(self.rfile.read(length))
            query, model, top_k, cutoff = validate_request(payload, len(self.server.papers))
        except (ValueError, UnicodeError) as error:
            return self.send_json(400, {"error": str(error)})
        if not self.server.inference_lock.acquire(blocking=False):
            return self.send_json(409, {"error": "A ranking is already running. Retry when it finishes."})
        try:
            result = rank_dataset(self.server.papers, query, model, top_k, cutoff,
                                  cache_dir=ROOT / ".cache/embeddings")
            self.send_json(200, dict(result, result_source="live"))
        except Exception:
            LOG.exception("Ranking failed")
            self.send_json(500, {"error": "Embedding calculation failed. Check the server log and model download connection."})
        finally:
            self.server.inference_lock.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/papers_sample.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with WorkbenchServer(("127.0.0.1", args.port), args.dataset) as server:
        print(f"HEAsyn workbench: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
