"""Deterministic workbench tests; no external model or API is required."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np
from dashboard import WorkbenchServer, validate_request
from heasyn.retrieval.dataset import load_dataset, dataset_digest
from heasyn.retrieval.embedding import rank_dataset
from heasyn.extraction.pdf import parse_pdf

ROOT = Path(__file__).resolve().parents[1]


class FakeEncoder:
    max_seq_length = 10

    def __init__(self):
        self.document_calls = 0

    def encode_document(self, documents, **kwargs):
        self.document_calls += 1
        return np.array([[1., 0.], [0., 1.]])

    def encode_query(self, queries, **kwargs):
        return np.array([[1., 0.]])

    def tokenizer(self, documents, **kwargs):
        return {"input_ids": [[1] * 5, [1] * 20]}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.papers = [{"paper_id": "a", "title": "Alpha", "abstract": "Alpha abstract", "category": "expert_curated"},
                       {"paper_id": "b", "title": "Beta", "abstract": "Beta abstract", "category": "out_of_domain"}]

    def test_bundled_dataset(self):
        papers = load_dataset(ROOT / "data/papers_sample.json")
        self.assertEqual(len(papers), 80)
        self.assertEqual(len({p["paper_id"] for p in papers}), 80)
        self.assertEqual(len({p["category"] for p in papers}), 4)

    def test_digest_changes_with_content(self):
        original = dataset_digest(self.papers)
        self.papers[0]["abstract"] += " changed"
        self.assertNotEqual(original, dataset_digest(self.papers))

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "papers.json"
            path.write_text(json.dumps([self.papers[0], self.papers[0]]))
            with self.assertRaises(ValueError):
                load_dataset(path)

    def test_ranking_cache_threshold_and_truncation(self):
        encoder = FakeEncoder()
        with tempfile.TemporaryDirectory() as folder, patch("heasyn.retrieval.embedding.load_encoder", return_value=encoder):
            first = rank_dataset(self.papers, "query", "test-model", 2, .5, folder)
            second = rank_dataset(self.papers, "new query", "test-model", 2, .5, folder)
            self.assertEqual(encoder.document_calls, 1)
            self.assertEqual(first["ranking"][0]["paper_id"], "a")
            self.assertEqual(first["selected_ids"], ["a"])
            self.assertEqual(first["truncated_abstracts"], 1)
            self.assertEqual(first["ranking"], second["ranking"])

    def test_invalid_parameters(self):
        for payload in [{"query": ""}, {"query": "x", "top_k": True}, {"query": "x", "top_k": 81},
                        {"query": "x", "min_score": float("nan")}, {"query": "x", "model": "unknown"}, []]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_request(payload, 80)

    def test_pdf_text_and_blank_pages(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.pdf"
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_textbox(pymupdf.Rect(30, 30, 550, 750), "Synthetic parser fixture. " * 25)
                doc.new_page()
                doc.save(path)
            text, blank = parse_pdf(path)
            self.assertIn("Synthetic parser fixture", text)
            self.assertEqual(blank, [2])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = WorkbenchServer(("127.0.0.1", 0), ROOT / "data/papers_sample.json")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_config(self):
        with urlopen(self.url + "/api/config") as response:
            self.assertEqual(json.load(response)["total"], 80)

    def test_private_paths_unavailable(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/.env")
        self.assertEqual(error.exception.code, 404)

    def test_bad_request(self):
        request = Request(self.url + "/api/rank", data=b'{"query":""}', headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)

    def test_cross_origin_request_rejected(self):
        request = Request(self.url + "/api/rank", data=b'{}', headers={"Origin": "https://example.com", "Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_live_route(self):
        value = {"query": "x", "model": "test", "ranking": []}
        request = Request(self.url + "/api/rank", data=b'{"query":"x"}', headers={"Content-Type": "application/json"})
        with patch("dashboard.rank_dataset", return_value=value), urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["result_source"], "live")
