"""DGX Demo backend entry point.

FastAPI app wiring together the admin/monitoring surfaces:
  1. /api/models   - vLLM model selection / download / launch
  2. /api/mcp      - MCP server config + devtunnel exposure
  3. /api/rag      - document upload + vectorization
  4. /api/chat     - local test chat
  5. /api/copilot  - offline GitHub Copilot CLI / VS Code BYOK integration
  + /ws/metrics    - live dashboard metrics
  + /metrics       - Prometheus exposition (scraped by the Grafana stack)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    chat, copilot, docker_admin, mcp_admin, models, monitoring, rag, studio3d,
    tunnels,
)
from app.config import settings
from app.services.gpu_monitor import gpu_monitor
from app.services.rag_pipeline import rag_pipeline
from app.services.vllm_metrics import vllm_metrics_sampler


@asynccontextmanager
async def lifespan(app: FastAPI):
    gpu_monitor.start()
    vllm_metrics_sampler.start()
    try:
        rag_pipeline.refresh_stats()
    except Exception:
        pass
    yield
    await gpu_monitor.stop()
    await vllm_metrics_sampler.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models.router)
app.include_router(mcp_admin.router)
app.include_router(tunnels.router)
app.include_router(docker_admin.router)
app.include_router(studio3d.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(copilot.router)
app.include_router(monitoring.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}


# Serve the built frontend (frontend/dist) if present.
_frontend_dist = settings.repo_root / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True),
              name="frontend")
