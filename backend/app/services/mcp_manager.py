"""Manager that starts/stops the MCP server as a subprocess."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.state_store import load_state, save_state


@dataclass
class McpState:
    running: bool = False
    port: int = 0
    message: str = ""


class McpManager:
    def __init__(self) -> None:
        self.state = McpState(port=settings.mcp_port)
        self._proc: subprocess.Popen | None = None

    def get_config(self) -> dict:
        return load_state("mcp_config", {"meta_prompt": settings.mcp_meta_prompt})

    def set_config(self, meta_prompt: str) -> dict:
        cfg = {"meta_prompt": meta_prompt}
        save_state("mcp_config", cfg)
        return cfg

    def start(self) -> McpState:
        if self.state.running and self._proc and self._proc.poll() is None:
            return self.state
        backend_dir = Path(__file__).resolve().parents[2]  # backend/
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "app.services.mcp_server"],
            cwd=str(backend_dir),
        )
        self.state = McpState(running=True, port=settings.mcp_port,
                              message="Serveur MCP démarré.")
        return self.state

    def stop(self) -> McpState:
        if self._proc:
            self._proc.terminate()
            self._proc = None
        self.state = McpState(running=False, port=settings.mcp_port,
                             message="Serveur MCP arrêté.")
        return self.state

    def status(self) -> McpState:
        if self._proc and self._proc.poll() is not None:
            self.state.running = False
        return self.state


mcp_manager = McpManager()
