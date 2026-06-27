"""Central configuration for the DGX Demo backend.

All tunable paths and defaults live here. Values can be overridden with a
`.env` file at the repository root or via environment variables prefixed with
``DGX_DEMO_``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels up from this file (backend/app/config.py -> repo)
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DGX_DEMO_",
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

    # --- HuggingFace ---
    # Access token used as the default for model downloads. Required for gated
    # models (Llama, Gemma…) and gives higher rate limits / faster downloads.
    # Override in .env via DGX_DEMO_HF_TOKEN. Get one at:
    # https://huggingface.co/settings/tokens
    hf_token: str = ""
    # Enable the Rust-based hf_transfer accelerator for much faster downloads
    # (used automatically when the optional ``hf_transfer`` package is present).
    hf_enable_hf_transfer: bool = True

    # --- vLLM (Docker container or native CLI on GB10 / Blackwell aarch64) ---
    vllm_host: str = "127.0.0.1"
    vllm_port: int = 8001    # Public multi-arch image (linux/arm64 included). Override in .env if you
    # have a private NGC image.
    vllm_docker_image: str = "vllm/vllm-openai:latest"
    vllm_container_name: str = "dgx-demo-vllm"

    # --- Embeddings (fastembed, ONNX, multilingual) ---
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dim: int = 1024

    # --- Studio 3D (image -> 3D via TRELLIS.2, text -> image via diffusers) ---
    # TRELLIS.2 is an image-to-3D model and CANNOT be served by vLLM. It runs in
    # its own pipeline (requires the `trellis2` package from the official repo).
    trellis_model: str = "microsoft/TRELLIS.2-4B"
    # Runtime used to serve TRELLIS.2: "docker" (recommended; native CUDA exts
    # compiled inside the image) or "native" (import trellis2 from the venv).
    trellis_runtime: str = "docker"
    # Containerised runtime: the native CUDA extensions are compiled inside this
    # image so the host venv stays clean. The base image must ship CUDA + nvcc +
    # a matching PyTorch (NGC pytorch is multi-arch incl. GB10/Blackwell).
    trellis_docker_image: str = "dgx-demo-trellis:latest"
    trellis_container_name: str = "dgx-demo-trellis"
    trellis_base_image: str = "nvcr.io/nvidia/pytorch:25.04-py3"
    # CUDA arch list for the in-image native builds. The NGC PyTorch only knows
    # arches up to 12.0; GB10 (sm_121) runs the 12.0 PTX via JIT (+PTX). Do NOT
    # use 12.1 here (PyTorch rejects it as "Unknown CUDA arch").
    trellis_cuda_arch: str = "12.0+PTX"
    trellis_host: str = "127.0.0.1"
    trellis_port: int = 8002
    # Lightweight, fast, non-gated text-to-image model used to create an input
    # picture from a prompt (single-step turbo distillation). Override in .env.
    text_to_image_model: str = "stabilityai/sd-turbo"
    # Where generated images + GLB assets are written (served back to the viewer).
    studio_assets_dir: Path = REPO_ROOT / "appdata" / "studio3d"

    # --- Qdrant vector DB ---
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_collection: str = "ragdoclocal"

    # --- Ollama (offline GitHub Copilot backend) ---
    # Ollama exposes an OpenAI-compatible API consumed by the Copilot CLI and
    # VS Code chat in offline mode. Models are pulled from the dashboard.
    ollama_host: str = "127.0.0.1"
    ollama_port: int = 11434
    ollama_container_name: str = "dgx-demo-ollama"
    ollama_image: str = "ollama/ollama:0.30.10"

    # --- Grafana (embedded observability dashboards) ---
    # Port the Grafana container publishes; the dashboard embeds it in an iframe.
    grafana_port: int = 3000
    # UID of the provisioned dashboard (see observability/grafana/dashboards).
    grafana_dashboard_uid: str = "ollama-copilot"

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

    # --- Energy & carbon footprint (defaults for France) ---
    # Carbon intensity of the French electricity mix (gCO2eq per kWh). France is
    # very low-carbon thanks to nuclear power; ADEME reference ~ 56 gCO2eq/kWh.
    carbon_intensity_g_per_kwh: float = 56.0
    # Fallback average power draw (W) used to estimate per-request energy when no
    # live GPU power sample is available (e.g. metrics pushed by the MCP worker).
    inference_power_w: float = 240.0

    # --- Dashboard (frontend) ---
    # Vite dev server port. The tunnel exposes this so hot-reload dev works.
    dashboard_port: int = 5173

    # --- GitHub OAuth (issue reporting via Device Flow) ---
    # Client ID of a GitHub OAuth App with "Device Flow" enabled. Required to
    # request the ``repo`` scope. Override in .env via DGX_DEMO_GITHUB_CLIENT_ID.
    github_client_id: str = ""
    github_oauth_scope: str = "repo"

    @property
    def vllm_base_url(self) -> str:
        return f"http://{self.vllm_host}:{self.vllm_port}/v1"

    @property
    def trellis_base_url(self) -> str:
        return f"http://{self.trellis_host}:{self.trellis_port}"

    @property
    def ollama_base_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}"

    @property
    def ollama_openai_url(self) -> str:
        return f"http://{self.ollama_host}:{self.ollama_port}/v1"

    def ensure_dirs(self) -> None:
        for d in (self.rag_docs_dir, self.models_dir, self.state_dir,
                  self.studio_assets_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings


settings = get_settings()
