"""Admin interface 1: vLLM model selection, download and launch."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.hf_downloader import download_manager
from app.services.state_store import save_state
from app.services.vllm_manager import LaunchParams, vllm_manager
from app.config import settings

router = APIRouter(prefix="/api/models", tags=["models"])


class DownloadRequest(BaseModel):
    model_id: str
    hf_token: str | None = None


class LaunchRequest(BaseModel):
    model: str
    served_model_name: str = ""
    dtype: str = "auto"
    quantization: str | None = None
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.90
    tensor_parallel_size: int = 1
    max_num_seqs: int = 256
    trust_remote_code: bool = True
    enforce_eager: bool = False
    enable_auto_tool_choice: bool = False
    tool_call_parser: str = ""
    extra_args: str = ""
    runtime: str = "docker"


@router.get("/curated")
def curated():
    return {"models": download_manager.curated()}


@router.get("/search")
def search(q: str = "", limit: int = 20):
    return {"results": download_manager.search(q, limit)}


@router.get("/downloaded")
def downloaded():
    return {"models": download_manager.downloaded_models()}


@router.post("/download")
def download(req: DownloadRequest):
    job = download_manager.start_download(req.model_id, req.hf_token)
    return {"job": job.__dict__}


@router.get("/download/status")
def download_status(model_id: str):
    job = download_manager.get_job(model_id)
    return {"job": job.__dict__ if job else None}


@router.get("/downloads")
def downloads():
    return {"jobs": [j.__dict__ for j in download_manager.all_jobs()]}


@router.delete("/downloaded")
def delete_downloaded(model_id: str):
    return download_manager.delete_model(model_id)


@router.post("/launch")
async def launch(req: LaunchRequest):
    params = LaunchParams(**req.model_dump())
    state = vllm_manager.launch(params)
    save_state("vllm_state", {"model": state.model, "running": state.running})
    return {"state": state.__dict__}


@router.post("/stop")
def stop():
    state = vllm_manager.stop()
    save_state("vllm_state", {"model": "", "running": False})
    return {"state": state.__dict__}


@router.get("/status")
async def status(request: Request):
    state = await vllm_manager.health()
    # Build a browser-reachable URL based on the current API host.
    host = request.url.hostname or "127.0.0.1"
    state["exposed_url"] = f"http://{host}:{settings.vllm_port}"
    state["openai_api_url"] = f"http://{host}:{settings.vllm_port}/v1"
    return state
