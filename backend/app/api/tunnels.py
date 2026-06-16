"""Admin interface: DevTunnel management.

Create / list / delete named Microsoft dev tunnels exposing local ports
(e.g. the dashboard on 5173 and the MCP server on 9000) to the internet,
tied to a GitHub account.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.services.devtunnel_manager import devtunnel_manager

router = APIRouter(prefix="/api/tunnels", tags=["tunnels"])


class CreateRequest(BaseModel):
    name: str
    port: int
    protocol: str = "http"


class NameRequest(BaseModel):
    name: str


@router.get("/defaults")
def defaults():
    """Suggested tunnels for this deployment (dashboard + MCP server)."""
    return {
        "tunnels": [
            {"name": "dashboard", "port": settings.dashboard_port},
            {"name": "mcp", "port": settings.mcp_port},
        ]
    }


# --- GitHub login ---

@router.get("/login-status")
def login_status():
    return devtunnel_manager.login_status().__dict__


@router.post("/login")
def login():
    return devtunnel_manager.login_github().__dict__


# --- Tunnels ---

@router.get("/list")
def list_tunnels():
    return {"tunnels": devtunnel_manager.list_tunnels()}


@router.post("/create")
def create(req: CreateRequest):
    return devtunnel_manager.create_tunnel(req.name, req.port, req.protocol)


@router.post("/stop")
def stop(req: NameRequest):
    return devtunnel_manager.stop_tunnel(req.name)


@router.post("/delete")
def delete(req: NameRequest):
    return devtunnel_manager.delete_tunnel(req.name)
