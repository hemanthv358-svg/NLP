import difflib
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone

import mysql.connector

from backend.app.config import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
    UNIVERSITY_URL,
)
from backend.app.crawler import canonical_site_key
from backend.app.seed_data import SEED_DOCUMENTS


STOP_TERMS = {
    "about", "and", "are", "does", "for", "from", "has", "have", "how", "into", "its",
    "many", "more", "that", "the", "their", "this", "what", "when", "where", "which", "with",
}


@contextmanager
def connect():
    if not MYSQL_PASSWORD:
        raise RuntimeError("MYSQL_PASSWORD is not set. Copy .env.example to .env and add the app user's password.")
    connection = mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        connection_timeout=10,
    )
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                source_type VARCHAR(16) NOT NULL,
                source_site VARCHAR(255) NOT NULL,
                source_url TEXT NOT NULL,
                title VARCHAR(512) NOT NULL,
                content LONGTEXT NOT NULL,
                metadata JSON NULL,
                fetched_at DATETIME(6) NOT NULL,
                FULLTEXT KEY documents_search (title, content),
                KEY documents_source_type (source_type),
                KEY documents_source_site (source_site)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
            """
        )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'documents' AND column_name = 'source_site'
            """,
            (MYSQL_DATABASE,),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                "ALTER TABLE documents ADD COLUMN source_site VARCHAR(255) NOT NULL DEFAULT '' AFTER source_type, "
                "ADD KEY documents_source_site (source_site)"
            )
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'documents' AND column_name = 'metadata'
            """,
            (MYSQL_DATABASE,),
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute("ALTER TABLE documents ADD COLUMN metadata JSON NULL AFTER content")
        default_site = canonical_site_key(UNIVERSITY_URL)
        cursor.execute("UPDATE documents SET source_site = %s WHERE source_site = ''", (default_site,))
        cursor.execute(
            "SELECT COUNT(*) FROM documents WHERE source_type = 'seed' AND source_site = %s",
            (default_site,),
        )
        local_count = cursor.fetchone()[0]
        if local_count == 0:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cursor.executemany(
                "INSERT INTO documents(source_type, source_site, source_url, title, content, metadata, fetched_at) "
                "VALUES ('seed', %s, %s, %s, %s, %s, %s)",
                [
                    (
                        default_site,
                        UNIVERSITY_URL,
                        f"{topic}: {question}",
                        answer,
                        json.dumps({"kind": "seed", "topic": topic}),
                        now,
                    )
                    for topic, question, answer in SEED_DOCUMENTS
                ],
            )
        cursor.close()


def replace_web_documents(source_site, documents):
    if not documents:
        raise ValueError("The crawl returned no usable content; existing web knowledge was preserved.")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM documents WHERE source_type = 'web' AND source_site = %s",
            (source_site,),
        )
        cursor.executemany(
            "INSERT INTO documents(source_type, source_site, source_url, title, content, metadata, fetched_at) "
            "VALUES ('web', %s, %s, %s, %s, %s, %s)",
            [
                (
                    source_site,
                    item["url"],
                    item["title"],
                    item["content"],
                    json.dumps(item.get("metadata", {})),
                    now,
                )
                for item in documents
            ],
        )
        cursor.close()


def rank_documents(query, candidates, limit=6, fulltext_scores=None):
    terms = [
        term for term in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(term) > 2 and term not in STOP_TERMS
    ][:12]
    if not terms:
        terms = [term for term in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(term) > 1][:12]
    fulltext_scores = fulltext_scores or {}

    def lexical_score(document):
        title_tokens = set(re.findall(r"[a-zA-Z0-9]+", document["title"].lower()))
        content_tokens = set(re.findall(r"[a-zA-Z0-9]+", document["content"].lower()))
        score = fulltext_scores.get(document["id"], 0.0)
        for term in terms:
            if term in title_tokens:
                score += 4
            elif term in content_tokens:
                score += 2
            else:
                best_match = max(
                    (difflib.SequenceMatcher(None, term, token).ratio() for token in content_tokens),
                    default=0,
                )
                if best_match >= 0.82:
                    score += best_match
        return score

    ranked = sorted(
        ((lexical_score(document), document) for document in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    matches = [document for score, document in ranked if score > 0]
    return (matches or candidates)[:limit]


def search_documents(query, source_site, limit=6):
    terms = [
        term for term in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(term) > 2 and term not in STOP_TERMS
    ][:12]
    if not terms:
        terms = [term for term in re.findall(r"[a-zA-Z0-9]+", query.lower()) if len(term) > 1][:12]
    search_text = " ".join(terms)
    with connect() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT d.id, d.source_type, d.source_url, d.title, d.content,
                   MATCH(d.title, d.content) AGAINST (%s IN NATURAL LANGUAGE MODE) AS relevance_score
            FROM documents d
            WHERE d.source_site = %s
              AND MATCH(d.title, d.content) AGAINST (%s IN NATURAL LANGUAGE MODE)
            ORDER BY relevance_score DESC
            LIMIT %s
            """,
            (search_text, source_site, search_text, limit),
        )
        fulltext_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT id, source_type, source_url, title, content
            FROM documents
            WHERE source_site = %s
            ORDER BY fetched_at DESC
            LIMIT 500
            """,
            (source_site,),
        )
        candidates = cursor.fetchall()
        cursor.close()
    fulltext_scores = {
        row["id"]: float(row.get("relevance_score") or 0)
        for row in fulltext_rows
    }
    return rank_documents(query, candidates, limit, fulltext_scores)


def knowledge_stats(source_site):
    with connect() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT source_type, COUNT(*) AS count FROM documents WHERE source_site = %s GROUP BY source_type",
            (source_site,),
        )
        counts = {
            row["source_type"]: row["count"]
            for row in cursor.fetchall()
        }
        cursor.execute(
            "SELECT MAX(fetched_at) AS last_refresh FROM documents "
            "WHERE source_type = 'web' AND source_site = %s",
            (source_site,),
        )
        last_refresh = cursor.fetchone()["last_refresh"]
        cursor.close()
    return {
        "seed_documents": counts.get("seed", 0),
        "web_chunks": counts.get("web", 0),
        "total_documents": sum(counts.values()),
        "last_refresh": last_refresh,
        "source_site": source_site,
    }


def export_documents(source_site):
    with connect() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT source_type, source_site, source_url, title, content, metadata, fetched_at "
            "FROM documents WHERE source_site = %s ORDER BY id",
            (source_site,),
        )
        rows = cursor.fetchall()
        cursor.close()
    for row in rows:
        if hasattr(row["fetched_at"], "isoformat"):
            row["fetched_at"] = row["fetched_at"].isoformat()
    return rows
