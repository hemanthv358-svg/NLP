# Architecture

## Request flow

1. The dependency-free frontend sends a validated chat request to FastAPI.
2. The backend derives a canonical domain from the selected website and uses hybrid full-text and typo-tolerant retrieval only within that domain.
3. Only the highest-ranked records are added to the Ollama prompt.
4. Ollama tokens stream back as newline-delimited JSON; analysis requests may also emit a validated chart event.
5. The frontend renders the answer, source links, and optional native canvas chart incrementally, and can cancel active generation.

## Knowledge refresh

The gather endpoint validates a user-selected public URL, starts a background crawler, and returns immediately. The crawler stays on the selected domain, renders pages with headless Chromium, extracts text and structured HTML tables, and falls back to direct HTML requests. It blocks local/private destinations and unsafe redirects. Gathered documents remain in a temporary preview buffer. The separate store endpoint replaces only that domain's old web chunks in one MySQL transaction, so gathering failures cannot erase working knowledge or data collected from another domain. Variable structures are stored in a JSON metadata column while the relational ownership and search columns remain stable.

## Ownership

- `backend/app/main.py`: HTTP boundary and background job state.
- `backend/app/database.py`: schema, persistence, atomic replacement, and retrieval.
- `backend/app/crawler.py`: URL safety, same-site acquisition, browser fallback, and chunking.
- `backend/app/ollama_service.py`: local model boundary and streaming.
- `frontend/`: browser UI, presentation, and interaction state.
- `scripts/`: operator entry points.
- `backend/app/document_ingestion.py`: TXT, Markdown, and PDF extraction and chunking.
- `backend/app/document_watcher.py`: watchdog create, modify, move, and delete synchronization.
