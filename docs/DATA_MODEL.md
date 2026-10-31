# Data Model

MySQL is the durable source of truth. `documents` stores domain ownership, source URL, title, sanitized content, flexible JSON metadata, and timestamps. HTML tables are represented as JSON rows instead of creating arbitrary per-site SQL tables.

ChromaDB stores semantic vectors derived with `sentence-transformers/all-MiniLM-L6-v2`. Vector metadata contains only the canonical site, source URL, and title. Search merges semantic results with MySQL full-text and typo-tolerant results.
