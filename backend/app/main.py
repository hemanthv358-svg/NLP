import csv
import io
import json
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import STATIC_DIR, UNIVERSITY_URL
from backend.app.crawler import canonical_site_key, crawl_website, validate_public_url
from backend.app.database import (
    initialize_database,
    export_documents,
    knowledge_stats,
    rank_documents,
    replace_web_documents,
    search_documents,
)
from backend.app.ollama_service import analyze_documents, model_status, stream_model_answer
from backend.app.schemas import ChatRequest, CrawlRequest
from backend.app.vector_store import query_site, replace_site_documents
from backend.app.document_watcher import start_document_watcher


crawl_lock = threading.Lock()
crawl_state = {
    "running": False,
    "storing": False,
    "completed_pages": 0,
    "total_pages": 0,
    "current_url": "",
    "error": None,
    "last_result": None,
    "source_url": UNIVERSITY_URL,
    "pending_documents": None,
}
generation_lock = threading.Lock()
active_generations = {}


@asynccontextmanager
async def lifespan(_app):
    initialize_database()
    watcher = start_document_watcher()
    try:
        yield
    finally:
        watcher.stop()
        watcher.join(timeout=5)


app = FastAPI(title="Local Website Research Assistant", version="3.0", lifespan=lifespan)


def crawl_progress(completed, total, url):
    with crawl_lock:
        crawl_state.update(completed_pages=completed, total_pages=total, current_url=url)


def run_crawl(source_url):
    try:
        source_site = canonical_site_key(source_url)
        documents, page_count, errors = crawl_website(source_url, progress=crawl_progress)
        if not documents:
            raise ValueError("The crawl found no usable text or tables; existing stored data was preserved.")
        result = {
            "url": source_url,
            "site": source_site,
            "pages": page_count,
            "chunks": len(documents),
            "warnings": len(errors),
            "stored": False,
        }
        with crawl_lock:
            crawl_state.update(last_result=result, pending_documents=documents, error=None)
    except Exception as error:
        with crawl_lock:
            crawl_state.update(error=str(error))
    finally:
        with crawl_lock:
            crawl_state.update(running=False, current_url="")


@app.get("/api/status")
def status(site_url: str = UNIVERSITY_URL):
    try:
        source_site = canonical_site_key(site_url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with crawl_lock:
        current_crawl = {
            key: value for key, value in crawl_state.items() if key != "pending_documents"
        }
        preview_chunks = (
            len(crawl_state["pending_documents"])
            if crawl_state["pending_documents"]
            and crawl_state["last_result"]
            and crawl_state["last_result"]["site"] == source_site
            else 0
        )
    knowledge = knowledge_stats(source_site)
    knowledge["preview_chunks"] = preview_chunks
    return {"model": model_status(), "knowledge": knowledge, "crawl": current_crawl}


@app.post("/api/knowledge/refresh", status_code=202)
def refresh_knowledge(request: CrawlRequest):
    try:
        source_url = validate_public_url(str(request.url))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with crawl_lock:
        if crawl_state["running"] or crawl_state["storing"]:
            raise HTTPException(status_code=409, detail="A gather or store operation is already running.")
        crawl_state.update(
            running=True,
            completed_pages=0,
            total_pages=0,
            current_url="",
            error=None,
            last_result=None,
            source_url=source_url,
            pending_documents=None,
        )
    threading.Thread(
        target=run_crawl,
        args=(source_url,),
        daemon=True,
        name="knowledge-crawler",
    ).start()
    return {"message": "Website crawl started.", "url": source_url}


@app.post("/api/knowledge/store")
def store_knowledge():
    with crawl_lock:
        if crawl_state["running"] or crawl_state["storing"]:
            raise HTTPException(status_code=409, detail="A gather or store operation is already running.")
        documents = crawl_state["pending_documents"]
        result = crawl_state["last_result"]
        if not documents or not result:
            raise HTTPException(status_code=409, detail="Gather a website before storing it.")
        crawl_state["storing"] = True
    try:
        replace_web_documents(result["site"], documents)
        vector_warning = None
        try:
            replace_site_documents(result["site"], documents)
        except Exception as error:
            vector_warning = str(error)
    except Exception as error:
        with crawl_lock:
            crawl_state.update(storing=False, error=str(error))
        raise HTTPException(status_code=500, detail="The gathered data could not be stored.") from error
    with crawl_lock:
        stored_result = {**result, "stored": True, "vector_warning": vector_warning}
        crawl_state.update(
            storing=False,
            pending_documents=None,
            last_result=stored_result,
            error=None,
        )
    return {"message": "Gathered data stored in MySQL.", "result": stored_result}


@app.post("/api/chat")
def chat(request: ChatRequest):
    site_url = str(request.site_url or UNIVERSITY_URL)
    source_site = canonical_site_key(site_url)
    with crawl_lock:
        pending_documents = (
            list(crawl_state["pending_documents"])
            if crawl_state["pending_documents"]
            and crawl_state["last_result"]
            and crawl_state["last_result"]["site"] == source_site
            else None
        )
    retrieval_limit = 6
    if pending_documents:
        preview_candidates = [
            {
                "id": index,
                "source_type": "preview",
                "source_url": document["url"],
                "title": document["title"],
                "content": document["content"],
            }
            for index, document in enumerate(pending_documents, start=1)
        ]
        documents = rank_documents(request.question, preview_candidates, limit=retrieval_limit)
    else:
        documents = search_documents(request.question, source_site, limit=retrieval_limit)
        try:
            vector_documents = query_site(source_site, request.question, limit=retrieval_limit)
            vector_documents += query_site("local-documents", request.question, limit=retrieval_limit)
            seen = {(item["source_url"], item["title"]) for item in vector_documents}
            documents = vector_documents + [
                item for item in documents if (item["source_url"], item["title"]) not in seen
            ]
            documents = documents[:retrieval_limit]
        except Exception:
            pass
    request_id = request.request_id or str(uuid.uuid4())
    stop_event = threading.Event()
    with generation_lock:
        active_generations[request_id] = stop_event
    sources = [
        {
            "index": index,
            "title": document["title"],
            "url": document["source_url"],
            "source_type": document["source_type"],
        }
        for index, document in enumerate(documents, start=1)
    ]

    def response_stream():
        try:
            yield json.dumps({"type": "sources", "sources": sources, "request_id": request_id, "thinking_level": request.thinking_level}) + "\n"
            history = [item.model_dump() for item in request.history]
            analysis = analyze_documents(
                request.question,
                documents,
                request.style,
                source_site,
                stop_event,
                request.thinking_level,
            )
            if analysis:
                yield json.dumps({"type": "token", "content": analysis["answer"]}) + "\n"
                if analysis.get("chart"):
                    yield json.dumps({"type": "chart", "chart": analysis["chart"]}) + "\n"
            else:
                for token in stream_model_answer(
                    request.question,
                    documents,
                    history,
                    request.style,
                    source_site,
                    stop_event,
                    request.thinking_level,
                ):
                    yield json.dumps({"type": "token", "content": token}) + "\n"
            yield json.dumps({"type": "done", "stopped": stop_event.is_set()}) + "\n"
        finally:
            with generation_lock:
                active_generations.pop(request_id, None)

    return StreamingResponse(response_stream(), media_type="application/x-ndjson")


@app.post("/api/chat/{request_id}/stop")
def stop_chat(request_id: str):
    with generation_lock:
        stop_event = active_generations.get(request_id)
    if stop_event:
        stop_event.set()
    return {"stopped": bool(stop_event)}


@app.get("/api/knowledge/export")
def export_knowledge(site_url: str, format: str = "json"):
    rows = export_documents(canonical_site_key(site_url))
    if format == "json":
        return rows
    if format != "csv":
        raise HTTPException(status_code=400, detail="Export format must be json or csv.")
    output = io.StringIO()
    fields = ["source_type", "source_site", "source_url", "title", "content", "metadata", "fetched_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=website-data.csv"})


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
