"""Offline GitHub Copilot integration: status, tests, and launch helpers.

The CLI and VS Code chat run fully offline against the local Ollama endpoint.
This router reports the installed tooling, runs the four offline checks against a
single active model, and returns copy-ready launch config (env + VS Code
settings + the exact command to start the CLI).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.services.copilot_tester import copilot_tester
from app.services.ollama_manager import ollama_manager

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class TestRequest(BaseModel):
    model: str | None = None


@router.get("/status")
async def status():
    """Installed tooling + a short summary of the local Ollama endpoint."""
    cli = copilot_tester.cli_status()
    ollama = await ollama_manager.status()
    return {
        **cli,
        "ollama_up": ollama.get("endpoint_up", False),
        "ollama_models": [m["name"] for m in (ollama.get("models") or [])],
        "openai_url": settings.ollama_openai_url,
    }


@router.post("/test")
async def test(req: TestRequest):
    """Run the four offline checks against one active model."""
    return await copilot_tester.run_tests(req.model)


@router.get("/launch")
async def launch(model: str | None = None):
    """Copy-ready launch config for the CLI and VS Code chat."""
    resolved = await copilot_tester.resolve_model(model)
    env = copilot_tester.env_block(resolved)
    cli_export = "\n".join(f'export {k}="{v}"' for k, v in env.items())
    cli_command = f"{cli_export}\ncopilot"
    return {
        "model": resolved,
        "env": env,
        "cli_command": cli_command,
        "vscode_settings": copilot_tester.vscode_settings(resolved),
        "script": "./scripts/start-copilot-offline.sh"
                  + (f" --model {resolved}" if resolved else ""),
    }
