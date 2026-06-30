"""Ollama admin: container control + model pull/list/delete.

Backs the dashboard "Copilot Offline" page. Pulling streams NDJSON progress
straight from Ollama so the UI can render a live download bar.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.ollama_manager import ollama_manager

router = APIRouter(prefix="/api/ollama", tags=["ollama"])


class PullRequest(BaseModel):
    model: str


class ModelRequest(BaseModel):
    name: str


@router.get("/status")
async def status(request: Request):
    st = await ollama_manager.status()
    host = request.url.hostname or settings.ollama_host
    # Browser-reachable URLs (the configured host may be 127.0.0.1).
    st["browser_base_url"] = f"http://{host}:{settings.ollama_port}"
    st["browser_openai_url"] = f"http://{host}:{settings.ollama_port}/v1"
    return st


@router.get("/search")
async def search(q: str = "", limit: int = 24):
    """Search the public Ollama library (ollama.com)."""
    return {"results": await ollama_manager.search_library(q, limit)}


@router.get("/tags")
async def tags(name: str):
    """Available tags + sizes for a library model."""
    return {"tags": await ollama_manager.library_tags(name)}


@router.get("/models")
async def models():
    return {"models": await ollama_manager.list_models()}


@router.get("/show")
async def show(name: str):
    """Capabilities + chat template for a local model (``/api/show``)."""
    return await ollama_manager.model_info(name)


@router.get("/metrics")
async def metrics():
    """Live request count + throughput for the loaded Ollama model.

    Surfaced on the main dashboard next to the vLLM metrics.
    """
    return await ollama_manager.runtime_metrics()


@router.post("/pull")
async def pull(req: PullRequest):
    async def gen():
        async for line in ollama_manager.pull_stream(req.model):
            yield line + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/load")
async def load(req: ModelRequest):
    """Run a local model: load it into memory so it's ready to serve."""
    return await ollama_manager.load_model(req.name)


@router.post("/stop")
async def stop(req: ModelRequest):
    """Stop a running model: unload it from memory (keep_alive=0)."""
    return await ollama_manager.stop_model(req.name)


@router.delete("/models")
async def delete_model(name: str):
    return await ollama_manager.delete_model(name)


@router.post("/container/start")
def start_container():
    return ollama_manager.start_container()


@router.post("/container/stop")
def stop_container():
    return ollama_manager.stop_container()
