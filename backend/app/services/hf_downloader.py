"""HuggingFace model discovery + download manager.

Provides curated, DGX-Spark (GB10 / Blackwell, ~128 GB unified memory)
compatible model suggestions, a HuggingFace Hub search filtered to
vLLM-compatible text-generation models, and background snapshot downloads
with progress tracking.
"""
from __future__ import annotations

import fnmatch
import os
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, snapshot_download

from app.config import settings

# Enable the Rust-based accelerator for much faster downloads when available.
if settings.hf_enable_hf_transfer:
    try:
        import hf_transfer  # noqa: F401

        os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")
    except Exception:
        pass

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
    {
        "id": "microsoft/TRELLIS.2-4B",
        "label": "Microsoft TRELLIS.2 4B (Image → 3D)",
        "params": "4B",
        "approx_vram_gb": 24,
        "quant": "bf16",
        "note": "Génère un objet 3D (GLB) depuis une image. Servi par le Studio 3D, PAS par vLLM.",
        "gated": False,
        "kind": "image-to-3d",
    },
    {
        "id": "stabilityai/sd-turbo",
        "label": "Stable Diffusion Turbo (Texte → Image)",
        "params": "~1B",
        "approx_vram_gb": 7,
        "quant": "fp16",
        "note": "Crée une image rapide depuis un prompt, à donner en entrée de TRELLIS. Servi par le Studio 3D.",
        "gated": False,
        "kind": "text-to-image",
    },
]


@dataclass
class DownloadJob:
    model_id: str
    status: str = "pending"  # pending | downloading | done | error
    message: str = ""
    local_path: str = ""
    progress: float = 0.0  # 0-100
    downloaded_bytes: int = 0
    total_bytes: int = 0


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
                pipeline_tag="text-generation",
                sort="downloads",
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

    def delete_model(self, model_id: str) -> dict[str, Any]:
        """Delete a locally-downloaded model directory and forget its job."""
        base = settings.models_dir.resolve()
        target = (settings.models_dir / model_id).resolve()
        # Guard against path traversal: target must stay inside models_dir.
        if base not in target.parents:
            return {"ok": False, "error": "Chemin de modèle invalide."}
        if not target.exists() or not target.is_dir():
            return {"ok": False, "error": "Modèle introuvable en local."}
        shutil.rmtree(target)
        # Clean up an empty org/owner directory if it has no other models.
        parent = target.parent
        try:
            if parent != base and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass
        with self._lock:
            self._jobs.pop(model_id, None)
        return {"ok": True}

    _IGNORE_PATTERNS = ["*.pth", "*.onnx", "original/*"]

    def _expected_total_bytes(self, model_id: str, hf_token: str | None) -> int:
        """Sum of file sizes for the repo, excluding ignored patterns."""
        try:
            info = api.model_info(
                model_id, files_metadata=True, token=hf_token or None
            )
        except Exception:
            return 0
        total = 0
        for sib in getattr(info, "siblings", []) or []:
            name = sib.rfilename
            if any(fnmatch.fnmatch(name, pat) for pat in self._IGNORE_PATTERNS):
                continue
            total += getattr(sib, "size", None) or 0
        return total

    def _dir_size_bytes(self, path: str) -> int:
        base = Path(path)
        if not base.exists():
            return 0
        total = 0
        for f in base.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
        return total

    def start_download(self, model_id: str, hf_token: str | None = None) -> DownloadJob:
        # Fall back to the token configured in .env (VIBEMCP_HF_TOKEN).
        hf_token = hf_token or settings.hf_token or None
        with self._lock:
            existing = self._jobs.get(model_id)
            if existing and existing.status in ("pending", "downloading"):
                return existing
            job = DownloadJob(model_id=model_id, status="pending")
            self._jobs[model_id] = job

        def _run() -> None:
            job.status = "downloading"
            local_dir = self._local_dir(model_id)
            job.total_bytes = self._expected_total_bytes(model_id, hf_token)
            stop_monitor = threading.Event()

            def _monitor() -> None:
                while not stop_monitor.is_set():
                    job.downloaded_bytes = self._dir_size_bytes(local_dir)
                    if job.total_bytes > 0:
                        job.progress = min(
                            99.0, job.downloaded_bytes / job.total_bytes * 100.0
                        )
                    stop_monitor.wait(1.0)

            mon = threading.Thread(target=_monitor, daemon=True)
            mon.start()
            try:
                local_path = snapshot_download(
                    repo_id=model_id,
                    local_dir=local_dir,
                    token=hf_token or None,
                    ignore_patterns=self._IGNORE_PATTERNS,
                )
                job.local_path = str(local_path)
                job.downloaded_bytes = job.total_bytes or self._dir_size_bytes(local_dir)
                job.progress = 100.0
                job.status = "done"
                job.message = "Téléchargement terminé"
            except Exception as exc:
                job.status = "error"
                job.message = str(exc)
            finally:
                stop_monitor.set()

        threading.Thread(target=_run, daemon=True).start()
        return job


download_manager = DownloadManager()
