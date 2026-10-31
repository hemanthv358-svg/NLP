import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT_DIR / "frontend"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(ROOT_DIR / "chroma_data")))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DOCUMENT_DIR = Path(os.getenv("DOCUMENT_DIR", str(ROOT_DIR / "documents")))
load_dotenv(ROOT_DIR / ".env")

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "jssstu_app")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "jssstu_ai")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1")
THINKING_DEBUG = os.getenv("THINKING_DEBUG", "false").lower() in {"1", "true", "yes"}
UNIVERSITY_URL = os.getenv("UNIVERSITY_URL", "https://jssstuniv.in/")
MAX_CRAWL_PAGES = int(os.getenv("MAX_CRAWL_PAGES", "8"))
MAX_CRAWL_SECONDS = int(os.getenv("MAX_CRAWL_SECONDS", "180"))
MAX_CRAWL_CHUNKS = int(os.getenv("MAX_CRAWL_CHUNKS", "500"))
CHUNK_SIZE = 1_400
CHUNK_OVERLAP = 180
