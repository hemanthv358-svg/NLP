from pathlib import Path

from pypdf import PdfReader

from backend.app.config import CHUNK_OVERLAP, CHUNK_SIZE, DOCUMENT_DIR
from backend.app.crawler import chunk_text
from backend.app.vector_store import delete_source, upsert_source_documents


SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf"}


def extract_text(path):
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def ingest_file(path):
    path = Path(path).resolve()
    if path.suffix.lower() not in SUPPORTED_SUFFIXES or not path.is_file():
        return 0
    documents = [
        {"url": path.as_uri(), "title": f"{path.name} · Part {index}", "content": content}
        for index, content in enumerate(chunk_text(extract_text(path)), start=1)
    ]
    upsert_source_documents("local-documents", str(path), documents)
    return len(documents)


def remove_file(path):
    delete_source("local-documents", str(Path(path).resolve()))


def ingest_existing_documents():
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    return sum(ingest_file(path) for path in DOCUMENT_DIR.rglob("*") if path.suffix.lower() in SUPPORTED_SUFFIXES)
