"""Offline regression tests for collection and seven-step POP extraction."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from heasyn.config import DEFAULT_MODELS
from heasyn.retrieval.collection import deduplicate, collect_papers, download_pdf
from heasyn.retrieval.embedding import select_ranked
from heasyn.extraction.prompts import STEPS, MISSING
from heasyn.extraction.pop import build_prompt, validate_response, run_pop
from heasyn.extraction.client import LLMClient

class PipelineTests(unittest.TestCase):
    def test_deduplication(self):
        a = {"paper_id": "a", "title": "HEA Catalyst", "doi": "10/x"}
        b = {"paper_id": "b", "title": "Other title", "doi": "10/X"}
        self.assertEqual(deduplicate([a, b, dict(a)]), [a])

    def test_ranking_and_threshold(self):
        ranked, selected = select_ranked([{"paper_id": "a"}, {"paper_id": "b"}], [0.2, 0.9], 1, 0.5)
        self.assertEqual(selected[0]["paper_id"], "b")
        self.assertEqual(len(ranked), 2)

    def test_prompt_dependencies(self):
        text = "Literal {paper_text} and {#Catalyst} in the source."
        prompt = build_prompt(STEPS[2], text, {"Catalyst": [{"name": "PtCoNiCuMn"}]})
        self.assertIn(text, prompt)
        self.assertIn("PtCoNiCuMn", prompt)

    def test_invalid_schema(self):
        import jsonschema
        with self.assertRaises(jsonschema.ValidationError):
            validate_response('{"Catalyst":[{"name":"PtCo"}]}', STEPS[1])
        with self.assertRaises(ValueError):
            validate_response('{"Problem":[NaN]}', STEPS[0])

    def test_fenced_json(self):
        self.assertEqual(validate_response('```json\n{"Problem":["Not reported"]}\n```', STEPS[0]), {"Problem": [MISSING]})

    def test_seven_step_pipeline(self):
        calls = []
        def fake(prompt):
            index = len(calls)
            calls.append(prompt)
            return json.dumps(STEPS[index][4]).replace("<number or Not reported>", MISSING).replace("<yes or no>", "no").replace("<experimental/computational/both/hypothesis>", "hypothesis")
        with tempfile.TemporaryDirectory() as folder:
            result, status = run_pop("Example paper text", fake, Path(folder))
            self.assertEqual(status, "complete")
            self.assertEqual(set(result), {s[0] for s in STEPS})
            self.assertEqual(len(calls), 7)

    def test_empty_catalyst_stops(self):
        answers = iter(['{"Problem":["Not reported"]}', '{"Catalyst":[]}'])
        with tempfile.TemporaryDirectory() as folder:
            result, status = run_pop("Unrelated paper", lambda _: next(answers), Path(folder))
            self.assertEqual(status, "no_target_catalyst")
            self.assertNotIn("Performance", result)

    def test_invalid_json_retry(self):
        answers = iter(['bad JSON', '{"Problem":["Not reported"]}', '{"Catalyst":[]}'])
        with tempfile.TemporaryDirectory() as folder:
            _, status = run_pop("Example", lambda _: next(answers), Path(folder))
            self.assertEqual(status, "no_target_catalyst")
            self.assertTrue((Path(folder) / "01_Problem_attempt2.txt").exists())

    def test_search_pagination(self):
        first = MagicMock()
        first.__enter__.return_value = first
        first.json.return_value = {"data": [{"paperId": "a", "title": "One"}], "next": 1}
        second = MagicMock()
        second.__enter__.return_value = second
        second.json.return_value = {"data": [{"paperId": "b", "title": "Two", "abstract": "Text"}]}
        with patch("heasyn.retrieval.collection.http_request", side_effect=[first, second]) as request, patch("time.sleep"):
            papers = collect_papers(["HEA"], 2)
        self.assertEqual(len(papers), 2)
        self.assertEqual(request.call_args_list[1].kwargs["params"]["offset"], 1)
        self.assertEqual(papers[0]["abstract"], "")

    def test_invalid_pdf_download(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [b"<html>Not a PDF</html>"]
        with tempfile.TemporaryDirectory() as folder, patch("heasyn.retrieval.collection.http_request", return_value=response):
            path = Path(folder) / "paper.pdf"
            with self.assertRaises(ValueError):
                download_pdf("https://example.org/paper", path)
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix(".download").exists())

    def test_provider_payloads(self):
        from types import SimpleNamespace
        for provider in DEFAULT_MODELS:
            args = SimpleNamespace(provider=provider, model=None, max_prompt_chars=5000,
                                   max_output_tokens=100, base_url=None,
                                   ollama_url="http://localhost:11434", ollama_context_tokens=8192)
            response = MagicMock()
            response.__enter__.return_value = response
            if provider == "anthropic":
                response.json.return_value = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}
            elif provider == "ollama":
                response.json.return_value = {"done": True, "done_reason": "stop", "message": {"content": "{}"}}
            else:
                response.json.return_value = {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
            with patch("heasyn.extraction.client.credential", return_value="test-placeholder"), patch("heasyn.extraction.client.http_request", return_value=response) as request:
                self.assertEqual(LLMClient(args)("Extract a JSON object"), "{}")
                self.assertEqual(request.call_args.kwargs["json"]["model"], DEFAULT_MODELS[provider])
                if provider == "ollama":
                    self.assertEqual(request.call_args.kwargs["json"]["options"]["num_ctx"], 8192)


