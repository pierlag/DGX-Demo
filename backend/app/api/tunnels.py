"""Admin interface: DevTunnel management.

Create / list / delete named Microsoft dev tunnels exposing local ports
(e.g. the dashboard on 5173 and the MCP server on 9000) to the internet,
tied to a GitHub account.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.devtunnel_manager import devtunnel_manager
from app.services.github_manager import github_manager

router = APIRouter(prefix="/api/tunnels", tags=["tunnels"])


class CreateRequest(BaseModel):
    name: str
    port: int
    protocol: str = "http"


class NameRequest(BaseModel):
    name: str


class TokenRequest(BaseModel):
    token: str


class ReportRequest(BaseModel):
    repo: str
    name: str
    url: str = ""


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


@router.post("/logout")
def logout():
    return devtunnel_manager.logout_github().__dict__


# --- Tunnels ---

@router.get("/list")
def list_tunnels():
    return {"tunnels": devtunnel_manager.list_tunnels()}


@router.post("/create")
def create(req: CreateRequest):
    return devtunnel_manager.create_tunnel(req.name, req.port, req.protocol)


@router.post("/create-stream")
def create_stream(req: CreateRequest):
    """Stream NDJSON progress events while creating/hosting the tunnel."""
    def gen():
        for event in devtunnel_manager.create_tunnel_stream(
            req.name, req.port, req.protocol
        ):
            yield json.dumps(event) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.post("/stop")
def stop(req: NameRequest):
    return devtunnel_manager.stop_tunnel(req.name)


@router.post("/delete")
def delete(req: NameRequest):
    return devtunnel_manager.delete_tunnel(req.name)


# --- GitHub repo integration (issue reporting) ---

@router.get("/github/status")
def github_status():
    return github_manager.status()


@router.post("/github/device")
def github_device():
    return github_manager.start_device_flow()


@router.post("/github/token")
def github_set_token(req: TokenRequest):
    return github_manager.set_token(req.token)


@router.post("/github/logout")
def github_logout():
    return github_manager.clear()


@router.get("/github/repos")
def github_repos():
    return github_manager.list_repos()


@router.post("/github/report")
def github_report(req: ReportRequest):
    return github_manager.report_tunnel(req.repo, req.name, req.url)

