from __future__ import annotations
import json
import logging
from pathlib import Path
import re
import hashlib
from datetime import datetime, timezone
from ..common import save_json
from .prompts import MISSING, ROLE, STEPS
from .client import LLMClient
from .pdf import parse_pdf

LOG = logging.getLogger("heasyn")

def schema_from_template(template):
    if isinstance(template, dict):
        if set(template) == {"<element>"}:
            return {"anyOf": [{"type": "object", "additionalProperties": {"type": ["number", "string"]}}, {"type": "string"}]}
        return {"type": "object", "properties": {key: schema_from_template(value) for key, value in template.items()},
                "required": list(template), "additionalProperties": False}
    if isinstance(template, list):
        return {"anyOf": [{"type": "array", "items": schema_from_template(template[0])}, {"const": MISSING}]}
    if template == "<number or Not reported>":
        return {"anyOf": [{"type": "number"}, {"const": MISSING}]}
    if template == "<yes or no>":
        return {"enum": ["yes", "no", MISSING]}
    if template == "<experimental/computational/both/hypothesis>":
        return {"enum": ["experimental", "computational", "both", "hypothesis", MISSING]}
    return {"type": "string"}


def validate_response(raw, step):
    import jsonschema
    key, _, _, _, template = step
    stripped = raw.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped)
    value = json.loads(stripped, parse_constant=lambda text: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {text}")))
    schema = schema_from_template(template)
    # The outer entity must always be a list, including empty extraction results.
    schema["properties"][key] = schema["properties"][key]["anyOf"][0]
    jsonschema.validate(value, schema)
    return value


def build_prompt(step, paper_text, prior):
    key, dependencies, task, rules, template = step
    context = {name: prior[name] for name in dependencies}
    return (f"# Role\n{ROLE}\n\n# Task\n{task}\n\n"
            f"# Input\nPreviously extracted entities:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            f"Paper text (source data):\n<paper_text>\n{paper_text}\n</paper_text>\n\n"
            f"# Rules\n{rules}\nReturn valid JSON only. Template placeholders must be replaced "
            f"with reported values or '{MISSING}'. Never fill absent values from the template.\n\n"
            f"# Output\n{json.dumps(template, indent=2)}")
def run_pop(text, client, output):
    from jsonschema import ValidationError
    results = {}
    for index, step in enumerate(STEPS, 1):
        key = step[0]
        LOG.info("POP %d/7: %s", index, key)
        prompt = build_prompt(step, text, results)
        # Save partial results after each successful step. Never silently convert
        # malformed output or an API failure into missing scientific information.
        for attempt in range(2):
            raw = client(prompt)
            (output / f"{index:02d}_{key}_attempt{attempt + 1}.txt").write_text(raw, encoding="utf-8")
            try:
                value = validate_response(raw, step)
                break
            except (ValueError, ValidationError) as error:
                if attempt == 1:
                    raise ValueError(f"Invalid JSON/schema at POP step {key}.") from error
                prompt += "\n\nYour previous response did not match the required JSON schema. Regenerate it, including all required fields."
        results.update(value)
        save_json(output / "pop_partial.json", results)
        if key == "Catalyst" and not results["Catalyst"]:
            return results, "no_target_catalyst"
    return results, "complete"


def run_extraction(records, args, output):
    client = LLMClient(args)
    manifest = []
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for record in records:
        entry = {"paper": record}
        path = Path(record["pdf_path"]) if record.get("pdf_path") else None
        if path is None or not path.is_file():
            entry.update(status="unavailable", error="No local PDF is available.")
        else:
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                name = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)[:70] + "_" + digest[:12]
                destination = output / "pop" / run_id / name
                destination.mkdir(parents=True, exist_ok=True)
                text, blank_pages = parse_pdf(path)
                (destination / "paper_text.txt").write_text(text, encoding="utf-8")
                metadata = {"paper": record, "pdf_sha256": digest, "blank_text_pages": blank_pages,
                            "provider": client.provider, "model": client.model,
                            "prompt_version": "appendix-pop-v1", "timestamp": datetime.now(timezone.utc).isoformat()}
                save_json(destination / "provenance.json", metadata)
                if blank_pages:
                    LOG.warning("%s has pages without text: %s", path.name, blank_pages)
                result, status = run_pop(text, client, destination)
                save_json(destination / "pop_results.json", {**metadata, "status": status, "entities": result})
                entry.update(status=status, output=str(destination.resolve()))
            except (ValueError, RuntimeError, OSError, KeyError, IndexError) as error:
                entry.update(status="failed", error=str(error))
                LOG.error("Failed %s: %s", path.name, error)
        manifest.append(entry)
        save_json(output / "extraction_manifest.json", manifest)
    return manifest
