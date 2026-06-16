"""HuggingFace model discovery + download manager.

Provides curated, DGX-Spark (GB10 / Blackwell, ~128 GB unified memory)
compatible model suggestions, a HuggingFace Hub search filtered to
vLLM-compatible text-generation models, and background snapshot downloads
with progress tracking.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from huggingface_hub import HfApi, snapshot_download

from app.config import settings

api = HfApi()

# Curated picks known to run well on a single GB10 (DGX Spark) with vLLM.
# Sizes are approximate weight footprints; unified memory is ~128 GB.
CURATED_MODELS: list[dict[str, Any]] = [
    {
        "id": "meta-llama/Llama-3.1-8B-Instruct",
        "label": "Llama 3.1 8B Instruct",
        "params": "8B",
        "approx_vram_gb": 16,
        "quant": "bf16",
        "note": "Excellent baseline, multilingue, rapide.",
        "gated": True,
    },
    {
        "id": "Qwen/Qwen2.5-14B-Instruct",
        "label": "Qwen2.5 14B Instruct",
        "params": "14B",
        "approx_vram_gb": 30,
        "quant": "bf16",
        "note": "Très bon raisonnement, multilingue.",
        "gated": False,
    },
    {
        "id": "Qwen/Qwen2.5-32B-Instruct",
        "label": "Qwen2.5 32B Instruct",
        "params": "32B",
        "approx_vram_gb": 65,
        "quant": "bf16",
        "note": "Qualité élevée, tient en mémoire unifiée.",
        "gated": False,
    },
    {
        "id": "meta-llama/Llama-3.1-70B-Instruct",
        "label": "Llama 3.1 70B Instruct (FP8)",
        "params": "70B",
        "approx_vram_gb": 75,
        "quant": "fp8",
        "note": "Démo impressionnante en FP8 (Blackwell).",
        "gated": True,
    },
    {
        "id": "mistralai/Mistral-7B-Instruct-v0.3",
        "label": "Mistral 7B Instruct v0.3",
        "params": "7B",
        "approx_vram_gb": 15,
        "quant": "bf16",
        "note": "Léger et rapide.",
        "gated": False,
    },
    {
        "id": "google/gemma-2-9b-it",
        "label": "Gemma 2 9B IT",
        "params": "9B",
        "approx_vram_gb": 18,
        "quant": "bf16",
        "note": "Bon compromis qualité/taille.",
        "gated": True,
    },
    {
        "id": "microsoft/Phi-4-mini-instruct",
        "label": "Microsoft Phi-4 Mini Instruct",
        "params": "~4B",
        "approx_vram_gb": 10,
        "quant": "bf16",
        "note": "Très compact, bon raisonnement pour la taille.",
        "gated": False,
    },
]


@dataclass
class DownloadJob:
    model_id: str
    status: str = "pending"  # pending | downloading | done | error
    message: str = ""
    local_path: str = ""


class DownloadManager:
    def __init__(self) -> None:
        self._jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()

    def curated(self) -> list[dict[str, Any]]:
        return CURATED_MODELS

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search HF Hub for text-generation models likely vLLM-compatible."""
        results: list[dict[str, Any]] = []
        try:
            models = api.list_models(
                search=query or None,
                task="text-generation",
                sort="downloads",
                direction=-1,
                limit=limit,
            )
            for m in models:
                results.append({
                    "id": m.id,
                    "label": m.id,
                    "downloads": getattr(m, "downloads", 0) or 0,
                    "likes": getattr(m, "likes", 0) or 0,
                    "gated": bool(getattr(m, "gated", False)),
                    "tags": list(getattr(m, "tags", []) or [])[:8],
                })
        except Exception as exc:  # pragma: no cover - network dependent
            return [{"id": "", "label": f"Erreur de recherche: {exc}", "error": True}]
        return results

    def get_job(self, model_id: str) -> DownloadJob | None:
        with self._lock:
            return self._jobs.get(model_id)

    def all_jobs(self) -> list[DownloadJob]:
        with self._lock:
            return list(self._jobs.values())

    def downloaded_models(self) -> list[str]:
        """List models already present in the local models cache."""
        base = settings.models_dir
        if not base.exists():
            return []
        found = []
        for org in base.iterdir():
            if org.is_dir():
                for repo in org.iterdir():
                    if repo.is_dir():
                        found.append(f"{org.name}/{repo.name}")
        return found

    def _local_dir(self, model_id: str) -> str:
        return str(settings.models_dir / model_id.replace("/", "/"))

    def start_download(self, model_id: str, hf_token: str | None = None) -> DownloadJob:
        with self._lock:
            existing = self._jobs.get(model_id)
            if existing and existing.status in ("pending", "downloading"):
                return existing
            job = DownloadJob(model_id=model_id, status="pending")
            self._jobs[model_id] = job

        def _run() -> None:
            job.status = "downloading"
            try:
                local_path = snapshot_download(
                    repo_id=model_id,
                    local_dir=self._local_dir(model_id),
                    token=hf_token or None,
                    ignore_patterns=["*.pth", "*.onnx", "original/*"],
                )
                job.local_path = str(local_path)
                job.status = "done"
                job.message = "Téléchargement terminé"
            except Exception as exc:
                job.status = "error"
                job.message = str(exc)

        threading.Thread(target=_run, daemon=True).start()
        return job


download_manager = DownloadManager()
