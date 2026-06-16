"""Admin interface 2: MCP server config (meta prompt) + lifecycle.

Tunnel management lives in its own admin surface (see app/api/tunnels.py).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.mcp_manager import mcp_manager

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ConfigRequest(BaseModel):
    meta_prompt: str


@router.get("/config")
def get_config():
    return mcp_manager.get_config()


@router.post("/config")
def set_config(req: ConfigRequest):
    return mcp_manager.set_config(req.meta_prompt)


@router.post("/start")
def start_mcp():
    return mcp_manager.start().__dict__


@router.post("/stop")
def stop_mcp():
    return mcp_manager.stop().__dict__


@router.get("/status")
def mcp_status():
    return mcp_manager.status().__dict__

