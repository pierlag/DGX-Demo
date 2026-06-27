"""Copilot CLI / VS Code chat — offline BYOK integration endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.copilot_manager import copilot_manager
from app.services.metrics import metrics_store

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class SessionPayload(BaseModel):
    active: bool


@router.get("/status")
async def status():
    return await copilot_manager.status()


@router.post("/test")
async def run_tests():
    """Run the BYOK validation suite against the local vLLM server."""
    return await copilot_manager.run_validation()


@router.get("/config")
async def config():
    """Return the CLI env + VS Code provider config for the served model."""
    st = await copilot_manager.status()
    model = st["model"]
    return {
        "base_url": st["base_url"],
        "model": model,
        "cli_env": copilot_manager.cli_env(model),
        "vscode": copilot_manager.vscode_config(model),
    }


@router.post("/script")
async def write_script():
    """Generate scripts/start-copilot-offline.sh wired to the served model."""
    st = await copilot_manager.status()
    return copilot_manager.write_launch_script(st["model"])


@router.post("/session")
def set_session(payload: SessionPayload):
    """Flag whether an offline Copilot session is wired to vLLM (for metrics)."""
    metrics_store.set_copilot_session(payload.active)
    return {"ok": True, "session_active": payload.active}
