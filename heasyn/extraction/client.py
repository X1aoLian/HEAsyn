from __future__ import annotations
from ..common import credential, http_request
from ..config import DEFAULT_MODELS
from .prompts import SYSTEM

class LLMClient:
    def __init__(self, args):
        self.args = args
        self.model = args.model or DEFAULT_MODELS[args.provider]
        self.provider = args.provider
        if self.provider == "anthropic":
            self.key = credential("ANTHROPIC_API_KEY", required=True)
        elif self.provider == "openai":
            self.key = credential("OPENAI_API_KEY", required=True)
        else:
            self.key = ""

    def __call__(self, prompt):
        if len(prompt) > self.args.max_prompt_chars:
            raise ValueError("Prompt exceeds --max-prompt-chars; no text was truncated. Use a larger-context model and adjust the limit.")
        if self.provider == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": self.key, "anthropic-version": "2023-06-01"}
            payload = {"model": self.model, "system": SYSTEM,
                       "messages": [{"role": "user", "content": prompt}], "max_tokens": self.args.max_output_tokens}
        elif self.provider == "ollama":
            url = self.args.ollama_url.rstrip("/") + "/api/chat"
            headers = {}
            # A conservative byte-based bound avoids relying on Ollama's input
            # truncation. Reserve space for output and the chat template.
            upper_bound = len((SYSTEM + prompt).encode("utf-8")) + self.args.max_output_tokens + 1024
            if upper_bound > self.args.ollama_context_tokens:
                raise ValueError("Conservative input/output budget exceeds --ollama-context-tokens. Choose a suitable context size/model; the paper was not truncated.")
            payload = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM},
                                                          {"role": "user", "content": prompt}],
                       "format": "json", "stream": False,
                       "options": {"num_ctx": self.args.ollama_context_tokens,
                                   "num_predict": self.args.max_output_tokens}}
        else:
            base = self.args.base_url or "https://api.openai.com/v1"
            url = base.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
            payload = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM},
                                                          {"role": "user", "content": prompt}],
                       "response_format": {"type": "json_object"}, "max_tokens": self.args.max_output_tokens}
        with http_request("POST", url, headers=headers, json=payload) as response:
            body = response.json()
        if self.provider == "ollama":
            if not body.get("done") or body.get("done_reason") != "stop":
                raise ValueError("Ollama did not complete the response; check output/context limits.")
            return body["message"].get("content") or ""
        if self.provider == "anthropic":
            if body.get("stop_reason") != "end_turn":
                raise ValueError("Anthropic did not complete the response; check output/context limits.")
            return "\n".join(block["text"] for block in body.get("content", []) if block.get("type") == "text")
        choice = body["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError("Model response was incomplete or refused; check output/context limits.")
        return choice["message"].get("content") or ""
