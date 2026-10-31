import threading
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from backend.app.config import DOCUMENT_DIR
from backend.app.document_ingestion import SUPPORTED_SUFFIXES, ingest_existing_documents, ingest_file, remove_file


class DocumentHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            ingest_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            ingest_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and any(event.src_path.lower().endswith(suffix) for suffix in SUPPORTED_SUFFIXES):
            remove_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            remove_file(event.src_path)
            ingest_file(event.dest_path)


def start_document_watcher():
    ingest_existing_documents()
    observer = Observer()
    observer.schedule(DocumentHandler(), str(DOCUMENT_DIR), recursive=True)
    observer.start()
    return observer
