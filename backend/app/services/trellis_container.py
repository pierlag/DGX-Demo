"""Lifecycle manager for the TRELLIS.2 image->3D Docker container.

Building the image compiles the native CUDA extensions *inside* the container,
so the host venv stays clean. Once running, the container exposes an HTTP API
(``/health`` and ``/generate``) that the backend calls instead of importing
``trellis2`` in-process.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class TrellisContainer:
    def __init__(self) -> None:
        self._docker_bin: str | None = None
        self._build_thread: threading.Thread | None = None
        self._build_state: dict[str, Any] = {
            "building": False,
            "ok": None,
            "message": "",
            "log_tail": "",
        }

    # -- helpers ----------------------------------------------------------
    def _docker(self) -> str | None:
        if self._docker_bin is None:
            self._docker_bin = shutil.which("docker")
        return self._docker_bin

    def _dockerfile_dir(self) -> Path:
        return settings.repo_root / "docker" / "trellis"

    def image_exists(self) -> bool:
        docker = self._docker()
        if not docker:
            return False
        res = subprocess.run(
            [docker, "images", "-q", settings.trellis_docker_image],
            capture_output=True, text=True,
        )
        return bool(res.stdout.strip())

    def _container_running(self) -> bool:
        docker = self._docker()
        if not docker:
            return False
        res = subprocess.run(
            [docker, "inspect", "-f", "{{.State.Running}}", settings.trellis_container_name],
            capture_output=True, text=True,
        )
        return res.stdout.strip() == "true"

    # -- build ------------------------------------------------------------
    def build(self) -> dict[str, Any]:
        docker = self._docker()
        if not docker:
            return {"ok": False, "message": "Docker introuvable."}
        if self._build_state["building"]:
            return {"ok": True, "message": "Build déjà en cours."}

        def _run() -> None:
            self._build_state.update(building=True, ok=None,
                                     message="Construction de l'image…", log_tail="")
            cmd = [
                docker, "build",
                "-t", settings.trellis_docker_image,
                "--build-arg", f"BASE_IMAGE={settings.trellis_base_image}",
                "--build-arg", f"TORCH_CUDA_ARCH_LIST={settings.trellis_cuda_arch}",
                str(self._dockerfile_dir()),
            ]
            lines: list[str] = []
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    lines.append(line.rstrip())
                    self._build_state["log_tail"] = "\n".join(lines[-40:])
                code = proc.wait()
                if code == 0:
                    self._build_state.update(
                        building=False, ok=True, message="Image construite.")
                else:
                    self._build_state.update(
                        building=False, ok=False,
                        message=f"Échec du build (code {code}).")
            except Exception as exc:
                self._build_state.update(building=False, ok=False, message=str(exc))

        self._build_thread = threading.Thread(target=_run, daemon=True)
        self._build_thread.start()
        return {"ok": True, "message": "Build lancé."}

    # -- run --------------------------------------------------------------
    def start(self) -> dict[str, Any]:
        docker = self._docker()
        if not docker:
            return {"ok": False, "message": "Docker introuvable."}
        if not self.image_exists():
            return {"ok": False, "message": "Image absente. Lancez d'abord le build."}
        if self._container_running():
            return {"ok": True, "message": "Conteneur déjà démarré."}

        subprocess.run([docker, "rm", "-f", settings.trellis_container_name],
                       capture_output=True)

        model_path = settings.models_dir / settings.trellis_model
        hf_cache = Path.home() / ".cache" / "huggingface"
        cmd = [
            docker, "run", "-d", "--rm",
            "--name", settings.trellis_container_name,
            "--gpus", "all",
            "--ipc=host",
            "-p", f"{settings.trellis_port}:{settings.trellis_port}",
            "-e", f"TRELLIS_PORT={settings.trellis_port}",
            "-v", f"{hf_cache}:/root/.cache/huggingface",
        ]
        if model_path.exists():
            # Mount the already-downloaded snapshot to avoid re-downloading.
            cmd += ["-v", f"{model_path}:/models/trellis:ro",
                    "-e", "TRELLIS_MODEL=/models/trellis"]
        else:
            cmd += ["-e", f"TRELLIS_MODEL={settings.trellis_model}"]
        # The pipeline always pulls the (gated) DINOv3 image encoder from HF, so
        # the token must be passed regardless of how the main model is provided.
        if settings.hf_token:
            cmd += ["-e", f"HF_TOKEN={settings.hf_token}",
                    "-e", f"HUGGING_FACE_HUB_TOKEN={settings.hf_token}"]
        cmd.append(settings.trellis_docker_image)

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            return {"ok": False, "message": res.stderr.strip() or "Échec du démarrage."}
        return {"ok": True, "message": "Conteneur TRELLIS démarré (chargement du modèle…)."}

    def stop(self) -> dict[str, Any]:
        docker = self._docker()
        if docker:
            subprocess.run([docker, "rm", "-f", settings.trellis_container_name],
                           capture_output=True)
        return {"ok": True, "message": "Conteneur TRELLIS arrêté."}

    # -- status / health --------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "docker": self._docker() is not None,
            "image_built": self.image_exists(),
            "running": self._container_running(),
            "build": dict(self._build_state),
            "image": settings.trellis_docker_image,
            "base_image": settings.trellis_base_image,
            "port": settings.trellis_port,
        }

    def health(self) -> dict[str, Any]:
        url = f"{settings.trellis_base_url}/health"
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"ready": False, "model": settings.trellis_model, "error": ""}

    def generate(self, image_path: Path, out_path: Path,
                 params: dict[str, Any] | None = None) -> None:
        """POST the image (and generation params) to the container, write the GLB."""
        url = f"{settings.trellis_base_url}/generate"
        data = {k: str(v) for k, v in (params or {}).items()}
        with open(image_path, "rb") as fh:
            files = {"file": (image_path.name, fh, "application/octet-stream")}
            # Generation can be slow on large voxel grids; allow a long timeout.
            with httpx.Client(timeout=900.0) as client:
                r = client.post(url, files=files, data=data)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except Exception:
                msg = r.text
            raise RuntimeError(msg or f"HTTP {r.status_code}")
        out_path.write_bytes(r.content)


trellis_container = TrellisContainer()
