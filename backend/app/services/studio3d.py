"""Studio 3D backend: text->image (diffusers) and image->3D (TRELLIS.2).

TRELLIS.2 is an *image-to-3D* generative model. It is **not** an LLM and cannot
be served by vLLM. It runs in its own pipeline via the official ``trellis2``
package (https://github.com/microsoft/TRELLIS.2). A lightweight diffusers
text-to-image model (SD-Turbo by default) produces an input picture from a
prompt, which can then be fed to TRELLIS.

Both backends are imported lazily and degrade gracefully: if the heavy
dependencies are not installed, the API still works and reports a clear,
actionable status instead of crashing the server.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.metrics import metrics_store
from app.services.trellis_container import trellis_container


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _model_downloaded(model_id: str) -> bool:
    """True if the model snapshot exists under the local models cache."""
    return (settings.models_dir / model_id).exists()


def _local_or_remote(model_id: str) -> str:
    """Prefer a locally downloaded snapshot, else fall back to the HF repo id."""
    local = settings.models_dir / model_id
    return str(local) if local.exists() else model_id


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
@dataclass
class StudioJob:
    id: str
    kind: str  # "image" | "mesh"
    status: str = "pending"  # pending | queued | running | done | error
    message: str = ""
    progress: float = 0.0  # 0-100
    result_name: str = ""  # filename inside studio_assets_dir
    prompt: str = ""
    created: float = field(default_factory=time.time)
    image_name: str = ""  # source image (mesh jobs)
    params: dict[str, Any] = field(default_factory=dict)
    queue_position: int = 0  # 0 = running/not queued, >=1 = waiting in line

    def to_dict(self) -> dict[str, Any]:
        url = f"/api/studio3d/file/{self.result_name}" if self.result_name else ""
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "progress": round(self.progress, 1),
            "result_name": self.result_name,
            "result_url": url,
            "prompt": self.prompt,
            "image_name": self.image_name,
            "queue_position": self.queue_position,
        }


# --------------------------------------------------------------------------- #
# Text -> Image (diffusers)
# --------------------------------------------------------------------------- #
class ImageGenerator:
    def __init__(self) -> None:
        self.model_id = settings.text_to_image_model
        self._pipe: Any = None
        self.loading = False
        self.message = ""
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return _module_available("diffusers") and _module_available("torch")

    @property
    def loaded(self) -> bool:
        return self._pipe is not None

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "loaded": self.loaded,
            "loading": self.loading,
            "model": self.model_id,
            "downloaded": _model_downloaded(self.model_id),
            "message": self.message,
        }

    def load(self) -> None:
        """Load the diffusers pipeline (blocking; call from a worker thread)."""
        with self._lock:
            if self._pipe is not None or self.loading:
                return
            self.loading = True
            self.message = "Chargement du modèle texte→image…"
        try:
            import torch
            from diffusers import AutoPipelineForText2Image

            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            pipe = AutoPipelineForText2Image.from_pretrained(
                _local_or_remote(self.model_id),
                torch_dtype=dtype,
            )
            pipe = pipe.to(device)
            try:
                pipe.set_progress_bar_config(disable=True)
            except Exception:
                pass
            self._pipe = pipe
            self.message = f"Modèle texte→image prêt ({device})."
        except Exception as exc:  # pragma: no cover - heavy/env dependent
            self.message = f"Échec du chargement: {exc}"
            raise
        finally:
            self.loading = False

    def generate(
        self,
        prompt: str,
        seed: int | None = None,
        steps: int = 1,
        guidance_scale: float = 0.0,
        width: int = 512,
        height: int = 512,
        negative_prompt: str = "",
    ) -> str:
        """Generate an image, save it as PNG, return the filename."""
        if self._pipe is None:
            self.load()
        import torch

        generator = None
        if seed is not None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            generator = torch.Generator(device=device).manual_seed(int(seed))

        kwargs: dict[str, Any] = dict(
            prompt=prompt,
            num_inference_steps=max(1, int(steps)),
            guidance_scale=float(guidance_scale),
            generator=generator,
        )
        if width:
            kwargs["width"] = int(width)
        if height:
            kwargs["height"] = int(height)
        if negative_prompt and negative_prompt.strip():
            kwargs["negative_prompt"] = negative_prompt.strip()
        result = self._pipe(**kwargs)
        image = result.images[0]
        name = f"img_{uuid.uuid4().hex[:12]}.png"
        image.save(settings.studio_assets_dir / name)
        return name


# --------------------------------------------------------------------------- #
# Image -> 3D (TRELLIS.2)
# --------------------------------------------------------------------------- #
class TrellisGenerator:
    INSTALL_HINT = (
        "Le paquet `trellis2` est requis. Installez-le via le script "
        "scripts/setup_studio3d.sh ou suivez https://github.com/microsoft/TRELLIS.2 "
        "(nécessite CUDA toolkit + extensions natives). Alternative recommandée : "
        "utilisez le runtime « docker » (aucune compilation sur l'hôte)."
    )

    def __init__(self) -> None:
        self.model_id = settings.trellis_model
        self.runtime = settings.trellis_runtime  # "native" | "docker"
        self._pipeline: Any = None
        self.loading = False
        self.message = ""
        self._lock = threading.Lock()

    # -- native availability ---------------------------------------------
    @property
    def _native_available(self) -> bool:
        return _module_available("trellis2") and _module_available("o_voxel")

    @property
    def available(self) -> bool:
        if self.runtime == "docker":
            return trellis_container.status()["docker"]
        return self._native_available

    @property
    def loaded(self) -> bool:
        if self.runtime == "docker":
            return bool(trellis_container.health().get("ready"))
        return self._pipeline is not None

    def status(self) -> dict[str, Any]:
        if self.runtime == "docker":
            cont = trellis_container.status()
            health = trellis_container.health()
            msg = self.message
            if not cont["docker"]:
                msg = "Docker introuvable."
            elif not cont["image_built"]:
                msg = "Image TRELLIS non construite. Cliquez « Construire l'image »."
            elif not cont["running"]:
                msg = "Conteneur arrêté. Cliquez « Démarrer »."
            elif not health.get("ready"):
                msg = health.get("error") or "Chargement du modèle dans le conteneur…"
            else:
                msg = "Conteneur TRELLIS prêt."
            return {
                "available": cont["docker"],
                "loaded": bool(health.get("ready")),
                "loading": self.loading,
                "model": self.model_id,
                "downloaded": _model_downloaded(self.model_id),
                "message": msg,
                "runtime": "docker",
                "container": cont,
            }
        # native
        msg = self.message
        if not self._native_available and not msg:
            msg = self.INSTALL_HINT
        return {
            "available": self._native_available,
            "loaded": self.loaded,
            "loading": self.loading,
            "model": self.model_id,
            "downloaded": _model_downloaded(self.model_id),
            "message": msg,
            "runtime": "native",
        }

    def load(self) -> None:
        """Native: import + load the pipeline. Docker: start the container."""
        if self.runtime == "docker":
            res = trellis_container.start()
            self.message = res.get("message", "")
            if not res.get("ok"):
                raise RuntimeError(self.message)
            return
        if not self._native_available:
            self.message = self.INSTALL_HINT
            raise RuntimeError(self.INSTALL_HINT)
        with self._lock:
            if self._pipeline is not None or self.loading:
                return
            self.loading = True
            self.message = "Chargement de TRELLIS.2 (peut prendre du temps)…"
        try:
            os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
            os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
            from trellis2.pipelines import Trellis2ImageTo3DPipeline

            pipeline = Trellis2ImageTo3DPipeline.from_pretrained(
                _local_or_remote(self.model_id)
            )
            try:
                pipeline.cuda()
            except Exception:
                pass
            self._pipeline = pipeline
            self.message = "TRELLIS.2 prêt."
        except Exception as exc:  # pragma: no cover - heavy/env dependent
            self.message = f"Échec du chargement de TRELLIS.2: {exc}"
            raise
        finally:
            self.loading = False

    def generate(self, image_name: str, progress=None, params: dict[str, Any] | None = None) -> str:
        """Run image->3D, export a GLB, return the GLB filename."""
        params = params or {}
        src = settings.studio_assets_dir / image_name
        if not src.exists():
            raise FileNotFoundError(f"Image introuvable: {image_name}")
        name = f"mesh_{uuid.uuid4().hex[:12]}.glb"
        out = settings.studio_assets_dir / name

        if self.runtime == "docker":
            if progress:
                progress(20.0, "Envoi de l'image au conteneur TRELLIS…")
            trellis_container.generate(src, out, params)
            return name

        # native runtime
        if not self._native_available:
            raise RuntimeError(self.INSTALL_HINT)
        if self._pipeline is None:
            self.load()

        from PIL import Image
        import o_voxel

        image = Image.open(src).convert("RGBA")

        seed = int(params.get("seed", 42))
        pipeline_type = params.get("pipeline_type") or "1024_cascade"
        preprocess = bool(params.get("preprocess_image", True))
        geom = {
            "steps": int(params.get("geometry_steps", 12)),
            "guidance_strength": float(params.get("geometry_guidance", 7.5)),
        }
        tex = {
            "steps": int(params.get("texture_steps", 12)),
            "guidance_strength": float(params.get("texture_guidance", 1.0)),
        }
        texture_size = int(params.get("texture_size", 2048))

        if progress:
            progress(30.0, "Génération de la structure 3D…")
        mesh = self._pipeline.run(
            image,
            seed=seed,
            pipeline_type=pipeline_type,
            preprocess_image=preprocess,
            sparse_structure_sampler_params=geom,
            shape_slat_sampler_params=geom,
            tex_slat_sampler_params=tex,
        )[0]
        try:
            mesh.simplify(16777216)  # nvdiffrast vertex limit
        except Exception:
            pass

        if progress:
            progress(75.0, "Export du maillage GLB…")
        glb = o_voxel.postprocess.to_glb(
            vertices=mesh.vertices,
            faces=mesh.faces,
            attr_volume=mesh.attrs,
            coords=mesh.coords,
            attr_layout=mesh.layout,
            voxel_size=mesh.voxel_size,
            aabb=[[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]],
            decimation_target=1000000,
            texture_size=texture_size,
            remesh=True,
            remesh_band=1,
            remesh_project=0,
            verbose=False,
        )
        glb.export(str(out), extension_webp=True)
        return name


# --------------------------------------------------------------------------- #
# Manager (jobs + lifecycle)
# --------------------------------------------------------------------------- #
class StudioManager:
    def __init__(self) -> None:
        self.images = ImageGenerator()
        self.trellis = TrellisGenerator()
        self._jobs: dict[str, StudioJob] = {}
        self._lock = threading.Lock()
        self._history: list[dict[str, Any]] = []
        self._load_history()

        # 3D (mesh) generation queue: jobs are processed one at a time by a
        # single background worker so heavy TRELLIS runs never overlap.
        self._mesh_pending: list[str] = []      # queued job ids, in order
        self._mesh_current: str | None = None   # job id currently running
        self._mesh_cv = threading.Condition()
        self._mesh_worker = threading.Thread(
            target=self._run_mesh_worker, daemon=True
        )
        self._mesh_worker.start()

    # -- history ----------------------------------------------------------
    def _history_path(self) -> Path:
        return settings.studio_assets_dir / "_history.json"

    def _load_history(self) -> None:
        try:
            with open(self._history_path(), encoding="utf-8") as fh:
                data = json.load(fh)
            self._history = data if isinstance(data, list) else []
        except Exception:
            self._history = []

    def _save_history(self) -> None:
        try:
            with open(self._history_path(), "w", encoding="utf-8") as fh:
                json.dump(self._history, fh)
        except Exception:
            pass

    def _add_history(self, name: str, kind: str, prompt: str = "", source: str = "") -> None:
        if not name:
            return
        with self._lock:
            self._history = [h for h in self._history if h.get("name") != name]
            self._history.insert(0, {
                "name": name,
                "kind": kind,  # "image" | "mesh"
                "prompt": prompt,
                "source": source,
                "created": time.time(),
            })
            self._save_history()

    def register_image(self, name: str, prompt: str = "") -> None:
        """Record an uploaded/generated image in the history."""
        self._add_history(name, "image", prompt=prompt)

    def history(self) -> list[dict[str, Any]]:
        """Return history entries whose asset file still exists."""
        items: list[dict[str, Any]] = []
        with self._lock:
            snapshot = list(self._history)
        for h in snapshot:
            name = h.get("name", "")
            if not name or not (settings.studio_assets_dir / name).exists():
                continue
            entry = {**h, "url": f"/api/studio3d/file/{name}"}
            preview = h.get("preview")
            ppath = settings.studio_assets_dir / preview if preview else None
            if ppath is not None and ppath.exists():
                # Cache-bust on mtime so a re-capture replaces the old thumbnail.
                entry["preview_url"] = (
                    f"/api/studio3d/file/{preview}?v={int(ppath.stat().st_mtime)}"
                )
            items.append(entry)
        return items

    def set_preview(self, name: str, data_url: str) -> dict[str, Any]:
        """Save a captured PNG as the preview image for a generated asset."""
        path = (settings.studio_assets_dir / name).resolve()
        base = settings.studio_assets_dir.resolve()
        if base not in path.parents or not path.exists():
            return {"ok": False, "message": "Modèle introuvable."}
        try:
            b64 = data_url.split(",", 1)[1] if "," in data_url else data_url
            raw = base64.b64decode(b64)
        except Exception:
            return {"ok": False, "message": "Image invalide."}
        if not raw:
            return {"ok": False, "message": "Image vide."}
        preview_name = f"{name}.preview.png"
        try:
            (settings.studio_assets_dir / preview_name).write_bytes(raw)
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        with self._lock:
            for h in self._history:
                if h.get("name") == name:
                    h["preview"] = preview_name
                    break
            self._save_history()
        return {
            "ok": True,
            "preview": preview_name,
            "preview_url": f"/api/studio3d/file/{preview_name}",
        }

    def delete_asset(self, name: str) -> dict[str, Any]:
        """Delete an asset file and remove it from the history."""
        path = (settings.studio_assets_dir / name).resolve()
        base = settings.studio_assets_dir.resolve()
        if base not in path.parents:
            return {"ok": False, "message": "Nom invalide."}
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        with self._lock:
            preview = next(
                (h.get("preview") for h in self._history if h.get("name") == name),
                None,
            )
            self._history = [h for h in self._history if h.get("name") != name]
            self._save_history()
        if preview:
            try:
                (settings.studio_assets_dir / preview).unlink(missing_ok=True)
            except Exception:
                pass
        return {"ok": True}

    # -- status -----------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "image_gen": self.images.status(),
            "trellis": self.trellis.status(),
        }

    # -- loading ----------------------------------------------------------
    def load_image_gen(self) -> dict[str, Any]:
        if not self.images.available:
            return {"ok": False, "message": "diffusers/torch non installés."}
        threading.Thread(target=self._safe_load, args=(self.images,), daemon=True).start()
        return {"ok": True, "message": "Chargement du modèle texte→image lancé."}

    def load_trellis(self) -> dict[str, Any]:
        if not self.trellis.available:
            return {"ok": False, "message": self.trellis.INSTALL_HINT}
        threading.Thread(target=self._safe_load, args=(self.trellis,), daemon=True).start()
        return {"ok": True, "message": "Chargement de TRELLIS.2 lancé."}

    # -- TRELLIS runtime + container control ------------------------------
    def set_trellis_runtime(self, runtime: str) -> dict[str, Any]:
        if runtime not in ("native", "docker"):
            return {"ok": False, "message": "Runtime invalide."}
        self.trellis.runtime = runtime
        return {"ok": True, "runtime": runtime}

    def build_trellis_container(self) -> dict[str, Any]:
        return trellis_container.build()

    def start_trellis_container(self) -> dict[str, Any]:
        return trellis_container.start()

    def stop_trellis_container(self) -> dict[str, Any]:
        return trellis_container.stop()

    @staticmethod
    def _safe_load(gen: Any) -> None:
        try:
            gen.load()
        except Exception:
            pass

    # -- jobs -------------------------------------------------------------
    def get_job(self, job_id: str) -> StudioJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return recent jobs (newest first) so the UI can resume polling."""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.to_dict() for j in jobs]

    def _new_job(self, kind: str, prompt: str = "") -> StudioJob:
        job = StudioJob(id=uuid.uuid4().hex[:12], kind=kind, prompt=prompt)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def submit_image(self, prompt: str, seed: int | None = None,
                     params: dict[str, Any] | None = None) -> StudioJob:
        job = self._new_job("image", prompt=prompt)
        params = params or {}

        def _run() -> None:
            job.status = "running"
            job.progress = 10.0
            job.message = "Génération de l'image…"
            started = time.time()
            try:
                name = self.images.generate(
                    prompt,
                    seed,
                    steps=int(params.get("steps", 1)),
                    guidance_scale=float(params.get("guidance", 0.0)),
                    width=int(params.get("width", 512)),
                    height=int(params.get("height", 512)),
                    negative_prompt=params.get("negative_prompt", "") or "",
                )
                job.result_name = name
                job.progress = 100.0
                job.status = "done"
                job.message = "Image générée."
                self._add_history(name, "image", prompt=prompt)
                metrics_store.record_studio(
                    "image", time.time() - started,
                    label=prompt, model=self.images.model_id,
                )
            except Exception as exc:
                job.status = "error"
                job.message = str(exc)

        threading.Thread(target=_run, daemon=True).start()
        return job

    def submit_mesh(self, image_name: str, params: dict[str, Any] | None = None) -> StudioJob:
        """Enqueue a 3D (mesh) generation. Jobs run one at a time (FIFO)."""
        job = self._new_job("mesh")
        job.image_name = image_name
        job.params = params or {}
        job.status = "queued"
        job.message = "En file d'attente…"
        with self._mesh_cv:
            self._mesh_pending.append(job.id)
            self._refresh_positions_locked()
            self._mesh_cv.notify()
        return job

    # -- mesh queue -------------------------------------------------------
    def _refresh_positions_locked(self) -> None:
        """Recompute queue_position for pending mesh jobs (hold _mesh_cv)."""
        for idx, jid in enumerate(self._mesh_pending):
            job = self._jobs.get(jid)
            if job is not None:
                job.queue_position = idx + 1

    def _run_mesh_worker(self) -> None:
        """Background worker: process queued mesh jobs sequentially."""
        while True:
            with self._mesh_cv:
                while not self._mesh_pending:
                    self._mesh_cv.wait()
                job_id = self._mesh_pending.pop(0)
                self._mesh_current = job_id
                self._refresh_positions_locked()
            try:
                self._process_mesh(job_id)
            finally:
                with self._mesh_cv:
                    self._mesh_current = None

    def _process_mesh(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return

        def _progress(p: float, msg: str) -> None:
            job.progress = p
            job.message = msg

        job.status = "running"
        job.queue_position = 0
        job.progress = 5.0
        job.message = "Initialisation de TRELLIS.2…"
        started = time.time()
        try:
            name = self.trellis.generate(job.image_name, progress=_progress,
                                         params=job.params)
            job.result_name = name
            job.progress = 100.0
            job.status = "done"
            job.message = "Modèle 3D généré."
            self._add_history(name, "mesh", source=job.image_name)
            metrics_store.record_studio(
                "mesh", time.time() - started,
                label=job.image_name, model=self.trellis.model_id,
            )
        except Exception as exc:
            job.status = "error"
            job.message = str(exc)

    def queue(self) -> list[dict[str, Any]]:
        """Return the running 3D job (position 0) plus pending jobs in order."""
        with self._mesh_cv:
            current = self._mesh_current
            pending = list(self._mesh_pending)
        out: list[dict[str, Any]] = []
        if current:
            job = self._jobs.get(current)
            if job is not None:
                out.append(job.to_dict())
        for jid in pending:
            job = self._jobs.get(jid)
            if job is not None:
                out.append(job.to_dict())
        return out


studio_manager = StudioManager()
