from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import time

LOG = logging.getLogger('heasyn')
def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def credential(variable, required=False):
    value = os.getenv(variable, "").strip()
    if value.upper().startswith(("YOUR_", "REPLACE_")):
        value = ""
    if required and not value:
        raise ValueError(f"Set {variable} to a real credential in your environment.")
    return value


def http_request(method, url, **kwargs):
    import requests
    for attempt in range(4):
        try:
            response = requests.request(method, url, timeout=(20, 180), **kwargs)
        except requests.RequestException:
            if attempt == 3:
                raise RuntimeError("Network request failed after four attempts.") from None
            time.sleep(2 ** attempt)
            continue
        if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
            retry_after = response.headers.get("Retry-After", "")
            wait = min(float(retry_after), 60) if retry_after.isdigit() else 2 ** (attempt + 1)
            response.close()
            time.sleep(wait)
            continue
        if not response.ok:
            status = response.status_code
            response.close()
            # Do not log headers, credentials, request bodies, or signed URLs.
            raise RuntimeError(f"HTTP {status}; verify endpoint, credentials, rate limit, and model access.")
        return response
    raise RuntimeError("Request retry budget exhausted.")
