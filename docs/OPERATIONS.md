# Operational Rules

- Respect `robots.txt`; operators remain responsible for target terms and applicable law.
- Wait a randomized 2–5 seconds between page requests and rotate a small transparent browser User-Agent pool.
- Bound every crawl by `MAX_CRAWL_PAGES`, `MAX_CRAWL_SECONDS`, `MAX_CRAWL_CHUNKS`, response-size limits, same-site traversal, and finite scroll attempts.
- Gathered data is temporary and queryable. **Store gathered data** atomically replaces that site's MySQL rows and then refreshes its Chroma vectors.
- Export stored records with `/api/knowledge/export?site_url=https://example.com&format=json` or `format=csv`.
- Rebuild the policy documents whenever crawler limits, secret handling, storage ownership, or browser isolation changes.
- Place `.txt`, `.md`, or `.pdf` files under `DOCUMENT_DIR`. Existing files ingest at startup; watchdog updates Chroma automatically without restarting FastAPI.
