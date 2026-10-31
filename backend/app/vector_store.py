import hashlib
import re
import threading

from backend.app.config import CHROMA_DIR, EMBEDDING_MODEL


_lock = threading.Lock()
_collection = None
_model = None


def _resources():
    global _collection, _model
    with _lock:
        if _collection is None:
            import chromadb
            from sentence_transformers import SentenceTransformer

            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            _collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_or_create_collection(
                "website_documents", metadata={"hnsw:space": "cosine"}
            )
            _model = SentenceTransformer(EMBEDDING_MODEL)
    return _collection, _model


def sanitize_scraped_text(value):
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(value))
    value = re.sub(
        r"(?im)^.*(?:ignore (?:all|any|the) previous|system prompt|developer message|act as|jailbreak).*$",
        "[removed untrusted instruction-like text]",
        value,
    )
    return re.sub(r"\s+", " ", value).strip()[:20_000]


def replace_site_documents(site, documents):
    collection, model = _resources()
    existing = collection.get(where={"site": site}, include=[])
    if existing.get("ids"):
        collection.delete(ids=existing["ids"])
    clean_documents = [sanitize_scraped_text(item["content"]) for item in documents]
    embeddings = model.encode(clean_documents, normalize_embeddings=True).tolist()
    ids = [hashlib.sha256(f"{site}:{index}:{item['url']}".encode()).hexdigest() for index, item in enumerate(documents)]
    collection.upsert(
        ids=ids,
        documents=clean_documents,
        embeddings=embeddings,
        metadatas=[{"site": site, "url": item["url"], "title": item["title"]} for item in documents],
    )


def query_site(site, query, limit=6):
    collection, model = _resources()
    embedding = model.encode([sanitize_scraped_text(query)], normalize_embeddings=True).tolist()
    result = collection.query(query_embeddings=embedding, n_results=limit, where={"site": site})
    return [
        {"source_type": "vector", "source_url": metadata["url"], "title": metadata["title"], "content": content}
        for metadata, content in zip(result.get("metadatas", [[]])[0], result.get("documents", [[]])[0])
    ]


def delete_source(site, source):
    collection, _ = _resources()
    collection.delete(where={"$and": [{"site": site}, {"source": source}]})


def upsert_source_documents(site, source, documents):
    collection, model = _resources()
    delete_source(site, source)
    if not documents:
        return
    clean = [sanitize_scraped_text(item["content"]) for item in documents]
    collection.upsert(
        ids=[hashlib.sha256(f"{site}:{source}:{index}".encode()).hexdigest() for index in range(len(documents))],
        documents=clean,
        embeddings=model.encode(clean, normalize_embeddings=True).tolist(),
        metadatas=[{"site": site, "source": source, "url": item["url"], "title": item["title"]} for item in documents],
    )
