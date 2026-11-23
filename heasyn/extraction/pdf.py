"""Text-only PDF parsing. No OCR or image interpretation."""
def parse_pdf(path):
    import pymupdf
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("Encrypted PDF requires a password.")
        pages = [page.get_text("text", sort=True).strip() for page in document]
    blank = [i + 1 for i, text in enumerate(pages) if not text]
    text = "\n\n".join(f"[Page {i + 1}]\n{value}" for i, value in enumerate(pages))
    if sum(len(p) for p in pages) < 200:
        raise ValueError("Insufficient PDF text; supply a text-based or OCR-processed PDF.")
    return text, blank
