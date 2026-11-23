from __future__ import annotations
import csv
import logging
from pathlib import Path
import re
import time

from ..common import credential, http_request, save_json
from .embedding import screen_papers

LOG = logging.getLogger("heasyn")

def deduplicate(papers):
    seen = set()
    result = []
    for paper in papers:
        identifiers = {str(paper.get("paper_id") or ""), str(paper.get("doi") or "").lower(),
                       re.sub(r"\W+", "", paper.get("title", "").casefold())} - {""}
        if identifiers & seen:
            continue
        seen.update(identifiers)
        result.append(paper)
    return result


def collect_papers(queries, limit):
    papers = []
    token = credential("SEMANTIC_SCHOLAR_API_KEY")
    headers = {"x-api-key": token} if token else {}
    fields = "paperId,title,abstract,year,authors,url,externalIds,openAccessPdf"
    for query in queries:
        offset = 0
        while offset < limit:
            with http_request("GET", "https://api.semanticscholar.org/graph/v1/paper/search",
                              headers=headers, params={"query": query, "offset": offset,
                                                       "limit": min(100, limit - offset), "fields": fields}) as response:
                payload = response.json()
            for item in payload.get("data", []):
                papers.append({"paper_id": item["paperId"], "title": item.get("title") or "",
                               "abstract": item.get("abstract") or "", "year": item.get("year"),
                               "authors": [a.get("name", "") for a in item.get("authors", [])],
                               "doi": (item.get("externalIds") or {}).get("DOI"),
                               "url": item.get("url"), "pdf_url": (item.get("openAccessPdf") or {}).get("url"),
                               "search_query": query})
            next_offset = payload.get("next")
            if next_offset is None or next_offset <= offset:
                break
            offset = next_offset
            time.sleep(1)
    return deduplicate(papers)
def download_pdf(url, destination):
    if not url or not url.lower().startswith(("https://", "http://")):
        raise ValueError("No usable open-access PDF URL; supply the paper locally.")
    destination = Path(destination)
    temporary = destination.with_suffix(".download")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with http_request("GET", url, stream=True) as response, temporary.open("wb") as output:
            size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 50 * 1024 * 1024:
                    raise ValueError("PDF download exceeds the 50 MiB limit.")
                output.write(chunk)
        with temporary.open("rb") as source:
            if b"%PDF-" not in source.read(1024):
                raise ValueError("The download is not a PDF (possibly a landing page).")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def run_collection(args, output):
    papers = collect_papers(args.search_query or [args.query], args.max_papers)
    save_json(output / "candidates.json", papers)
    ranked, selected = screen_papers(papers, args)
    save_json(output / "ranked_papers.json", ranked)
    with (output / "ranked_papers.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        columns = ["paper_id", "title", "year", "doi", "similarity", "url", "pdf_url"]
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ranked)
    for paper in selected:
        # Semantic Scholar identifiers are used only through a sanitized filename.
        name = re.sub(r"[^A-Za-z0-9_-]", "_", paper["paper_id"]) + ".pdf"
        destination = output / "pdfs" / name
        local = args.pdf_dir / name if args.pdf_dir else destination
        try:
            if local.is_file():
                destination = local
            elif not destination.is_file():
                download_pdf(paper["pdf_url"], destination)
            paper.update(pdf_path=str(destination.resolve()), pdf_status="available")
        except (RuntimeError, ValueError, OSError) as error:
            paper.update(pdf_status="unavailable", pdf_error=str(error))
            LOG.warning("PDF unavailable for %s: %s", paper["paper_id"], error)
    save_json(output / "selected_papers.json", selected)
    LOG.info("Collected %d unique records; selected %d papers.", len(papers), len(selected))
    return selected
