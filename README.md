# AtlasIQ

AtlasIQ is a private, local-first research assistant that turns public websites and local documents into a searchable knowledge base. It combines controlled web scraping, MySQL persistence, ChromaDB semantic search, sentence-transformer embeddings, and an Ollama-hosted local LLM to produce grounded answers with citations, charts, reports, persistent browser history, and configurable thinking depth.

## Features

- Playwright-rendered and BeautifulSoup static website gathering.
- Same-site crawling, `robots.txt`, request delays, cookie handling, and resource caps.
- Gather-preview-store workflow with isolated per-domain MySQL records.
- Local sentence-transformer embeddings and ChromaDB vector search.
- Incremental `.txt`, `.md`, and `.pdf` ingestion through watchdog.
- Hybrid semantic, full-text, and typo-tolerant retrieval.
- Ollama generation with citations and four thinking levels.
- Analysis charts, stop generation, message copying, local chat history, and Markdown reports.
- JSON/CSV exports and hardened non-root Docker deployment.

## Tech Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.11, FastAPI, Uvicorn |
| Local LLM | Ollama with Llama 3.1 or a compatible model |
| Gathering | Playwright, BeautifulSoup, `urllib`, `robots.txt` |
| Structured storage | MySQL 8.4+ / 26.x |
| Vector storage | ChromaDB |
| Embeddings | Sentence Transformers |
| Documents | pypdf, watchdog |
| Frontend | HTML, CSS, vanilla JavaScript, Canvas |
| Packaging | Docker, Docker Compose |

## Architecture

```text
Public website ──> crawler ──> preview ──> MySQL documents
                       │                       │
Local TXT/MD/PDF ─> watcher ─> chunking ──────┼──> ChromaDB vectors
                                               │
Question ──> hybrid retrieval (MySQL + Chroma) ┘
                         │
                  guarded RAG context
                         │
                  Ollama generation
                         │
             answer + citations + chart
```

MySQL is the durable source of truth. ChromaDB is a rebuildable semantic index. All scraped and local-document content is treated as untrusted before prompt construction.

## Project Structure

```text
AtlasIQ/
├── backend/
│   ├── app/
│   │   ├── config.py              Environment configuration
│   │   ├── crawler.py             Safe website gathering
│   │   ├── database.py            MySQL persistence and retrieval
│   │   ├── document_ingestion.py  TXT/Markdown/PDF ingestion
│   │   ├── document_watcher.py    Hot-reload file synchronization
│   │   ├── main.py                FastAPI routes and lifecycle
│   │   ├── ollama_service.py      Generation and thinking levels
│   │   ├── schemas.py             Request validation
│   │   ├── seed_data.py           Optional starter knowledge
│   │   └── vector_store.py        ChromaDB and embeddings
│   └── requirements.txt
├── frontend/                      HTML, CSS, JavaScript UI
├── docs/                          Architecture and guardrails
├── datasets/                      Existing JSS STU QA CSV/JSON datasets
├── papers/                        Project references and reports
├── project/                       Existing T5, BERT, and RoBERTa QA experiments
├── scripts/                       Windows launchers
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── bot.py
```

The `datasets/` and `project/` directories are preserved from the repository's earlier NLP question-answering work. AtlasIQ's production application lives under `backend/` and `frontend/`.

## Prerequisites

- Python 3.11
- MySQL Server and Workbench
- Ollama with `llama3.1` or another configured model
- Playwright Chromium
- Optional: Docker Desktop

## Setup

Create the database and restricted account in MySQL Workbench:

```sql
CREATE DATABASE IF NOT EXISTS jssstu_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER IF NOT EXISTS 'jssstu_app'@'localhost' IDENTIFIED BY 'YOUR_APP_PASSWORD';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP
    ON jssstu_ai.* TO 'jssstu_app'@'localhost';
```

Install and run:

```powershell
python -m pip install -r backend/requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
ollama pull llama3.1
python bot.py
```

Set `MYSQL_PASSWORD` in `.env`, keep `.env` private, then open `http://127.0.0.1:8000`.

## Local Documents

Add `.txt`, `.md`, or `.pdf` files under the configured `documents/` directory. Existing files ingest at startup; file additions, edits, moves, and deletions synchronize with ChromaDB without restarting FastAPI.

## Docker

```powershell
docker compose up --build
```

The container runs as a non-root user with dropped capabilities, a read-only root filesystem, resource limits, and persistent Chroma storage. MySQL remains external through `host.docker.internal`.

## Exports

```text
GET /api/knowledge/export?site_url=https://example.com&format=json
GET /api/knowledge/export?site_url=https://example.com&format=csv
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Operations](docs/OPERATIONS.md)
- [Security](docs/SECURITY.md)
- [Thinking Levels](docs/THINKING_LEVELS.md)

## License

No license has been selected. All rights remain with the repository owner unless a license is added later.
