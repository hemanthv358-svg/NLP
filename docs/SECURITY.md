# Security Rules

- Treat every scraped byte as untrusted. Remove executable markup, control characters, and instruction-like text before LLM use.
- Allow only public HTTP/HTTPS destinations on ports 80 and 443; block credentials, private addresses, unsafe redirects, and cross-site traversal.
- Keep `.env` out of source control. Production deployments should inject `MYSQL_PASSWORD` with an OS secret manager or Docker secret rather than baking it into images.
- Run Chromium and the API as UID 10001 with dropped capabilities, no new privileges, a read-only root filesystem, bounded memory/CPU, and writable storage only for Chroma.
- Do not render scraped HTML in the browser. Answers and citations use text-only DOM APIs.
- Chroma failure must not corrupt MySQL; MySQL remains authoritative and vector indexing can be retried.
- Treat watched local documents as untrusted input and restrict `DOCUMENT_DIR` permissions to the local operator.
