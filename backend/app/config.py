"""Central configuration for the vibeMCP backend.

All tunable paths and defaults live here. Values can be overridden with a
`.env` file at the repository root or via environment variables prefixed with
``VIBEMCP_``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels up from this file (backend/app/config.py -> repo)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VIBEMCP_",
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_name: str = "vibeMCP"
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Filesystem layout ---
    # Note: ``data/`` is reserved for Docker bind mounts (Qdrant) and may be
    # root-owned, so app-writable data lives under ``appdata/``.
    repo_root: Path = REPO_ROOT
    rag_docs_dir: Path = REPO_ROOT / "ragdoclocal"
    models_dir: Path = REPO_ROOT / "appdata" / "models"
    state_dir: Path = REPO_ROOT / "appdata" / "state"

    # --- vLLM (Docker container or native CLI on GB10 / Blackwell aarch64) ---
    vllm_host: str = "127.0.0.1"
    vllm_port: int = 8001
    # Public multi-arch image (linux/arm64 included). Override in .env if you
    # have a private NGC image.
    vllm_docker_image: str = "vllm/vllm-openai:latest"
    vllm_container_name: str = "vibemcp-vllm"

    # --- Embeddings (fastembed, ONNX, multilingual) ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024

    # --- Qdrant vector DB ---
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "ragdoclocal"

    # --- MCP server ---
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 9000
    mcp_meta_prompt: str = (
        "You are a helpful RAG assistant. Answer strictly using the provided "
        "context from the local document base. If the answer is not in the "
        "context, say you don't know. Cite the source file names."
    )

    # --- Monitoring ---
    metrics_history_minutes: int = 15
    metrics_sample_interval_s: float = 2.0

    # --- Dashboard (frontend) ---
    # Vite dev server port. The tunnel exposes this so hot-reload dev works.
    dashboard_port: int = 5173

    @property
    def vllm_base_url(self) -> str:
        return f"http://{self.vllm_host}:{self.vllm_port}/v1"

    def ensure_dirs(self) -> None:
        for d in (self.rag_docs_dir, self.models_dir, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
