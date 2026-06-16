"""Admin interface 3: RAG document upload + vectorization."""
from __future__ import annotations

from pathlib import Path

import aiofiles
from fastapi import APIRouter, UploadFile

from app.config import settings
from app.services.rag_pipeline import SUPPORTED_EXTS, rag_pipeline

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.get("/files")
def files():
    return {"files": rag_pipeline.list_files()}


@router.post("/upload")
async def upload(files: list[UploadFile]):
    saved = []
    skipped = []
    settings.rag_docs_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = Path(f.filename or "file").name
        if Path(name).suffix.lower() not in SUPPORTED_EXTS:
            skipped.append(name)
            continue
        dest = settings.rag_docs_dir / name
        async with aiofiles.open(dest, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                await out.write(chunk)
        saved.append(name)
    return {"saved": saved, "skipped": skipped}


@router.delete("/file")
def delete_file(name: str):
    target = (settings.rag_docs_dir / name).resolve()
    # Path traversal guard
    if not str(target).startswith(str(settings.rag_docs_dir.resolve())):
        return {"ok": False, "error": "Chemin invalide"}
    if target.exists():
        target.unlink()
        return {"ok": True}
    return {"ok": False, "error": "Fichier introuvable"}


@router.post("/index")
def index():
    return rag_pipeline.reindex_async().__dict__


@router.get("/index/status")
def index_status():
    return rag_pipeline.state.__dict__


@router.get("/stats")
def stats():
    rag_pipeline.refresh_stats()
    return {
        "files": len(rag_pipeline.list_files()),
        "collection": settings.qdrant_collection,
    }
