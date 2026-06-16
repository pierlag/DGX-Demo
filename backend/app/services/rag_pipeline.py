"""RAG pipeline: document ingestion, chunking, embedding and retrieval.

Uses Qdrant (local) for vector storage and fastembed (ONNX, ARM-friendly, no
torch) for multilingual embeddings. Supports .txt, .md, .pdf and .docx files
placed in the ragdoclocal directory.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.services.metrics import metrics_store

SUPPORTED_EXTS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


@dataclass
class IndexState:
    status: str = "idle"          # idle | running | done | error
    message: str = ""
    processed_files: int = 0
    total_files: int = 0
    chunks: int = 0


def _read_text(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md", ".markdown"):
            return path.read_text(encoding="utf-8", errors="ignore")
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if ext == ".docx":
            import docx
            d = docx.Document(str(path))
            return "\n".join(p.text for p in d.paragraphs)
    except Exception:
        return ""
    return ""


def _chunk(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


class RagPipeline:
    def __init__(self) -> None:
        self.state = IndexState()
        self._lock = threading.Lock()
        self._client: QdrantClient | None = None

    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                host=settings.qdrant_host, port=settings.qdrant_port, timeout=30
            )
            self._client.set_model(settings.embedding_model)
        return self._client

    def ensure_collection(self) -> None:
        c = self.client()
        existing = {col.name for col in c.get_collections().collections}
        if settings.qdrant_collection not in existing:
            c.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=c.get_fastembed_vector_params(),
            )

    def list_files(self) -> list[dict[str, Any]]:
        base = settings.rag_docs_dir
        files = []
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                files.append({
                    "name": str(p.relative_to(base)),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "ext": p.suffix.lower(),
                })
        return files

    def refresh_stats(self) -> None:
        try:
            self.ensure_collection()
            info = self.client().count(settings.qdrant_collection, exact=True)
            chunks = info.count
        except Exception:
            chunks = 0
        files = len(self.list_files())
        metrics_store.set_index_stats(files, chunks)

    def reindex_async(self) -> IndexState:
        with self._lock:
            if self.state.status == "running":
                return self.state
            self.state = IndexState(status="running", message="Indexation en cours...")

        def _run() -> None:
            try:
                self.ensure_collection()
                c = self.client()
                # Reset collection for a clean rebuild
                c.delete_collection(settings.qdrant_collection)
                self.ensure_collection()

                files = [
                    p for p in settings.rag_docs_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
                ]
                self.state.total_files = len(files)
                docs: list[str] = []
                metadatas: list[dict] = []
                ids: list[str] = []

                for i, path in enumerate(files):
                    text = _read_text(path)
                    for ci, chunk in enumerate(_chunk(text)):
                        docs.append(chunk)
                        metadatas.append({
                            "source": str(path.relative_to(settings.rag_docs_dir)),
                            "chunk": ci,
                        })
                        ids.append(str(uuid.uuid4()))
                    self.state.processed_files = i + 1

                if docs:
                    # fastembed handles embedding under the hood
                    c.add(
                        collection_name=settings.qdrant_collection,
                        documents=docs,
                        metadata=metadatas,
                        ids=ids,
                    )
                self.state.chunks = len(docs)
                self.state.status = "done"
                self.state.message = f"Indexé {len(files)} fichiers, {len(docs)} chunks."
                self.refresh_stats()
            except Exception as exc:
                self.state.status = "error"
                self.state.message = str(exc)

        threading.Thread(target=_run, daemon=True).start()
        return self.state

    def query(self, text: str, top_k: int = 4) -> list[dict[str, Any]]:
        try:
            self.ensure_collection()
            hits = self.client().query(
                collection_name=settings.qdrant_collection,
                query_text=text,
                limit=top_k,
            )
        except Exception:
            return []
        results = []
        for h in hits:
            meta = h.metadata or {}
            results.append({
                "text": meta.get("document", "") or getattr(h, "document", ""),
                "source": meta.get("source", "?"),
                "score": round(float(h.score), 4),
            })
        return results


rag_pipeline = RagPipeline()
