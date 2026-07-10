"""vLLM lifecycle manager with hybrid runtime support (Docker or native CLI).

Supports two runtimes:
  1. Docker : launches vLLM in an NGC/public container
  2. Natif CLI : launches vllm_openai_server as a subprocess (requires pip install vllm)

The UI lets users choose. Monitoring and parameters are identical regardless of runtime.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings


@dataclass
class LaunchParams:
    """Standard vLLM model-loading parameters exposed in the admin UI."""
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
    runtime: Literal["docker", "native"] = "docker"  # NEW: choice of runtime


@dataclass
class VllmState:
    running: bool = False
    model: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    container_id: str = ""
    message: str = ""
    error: str = ""  # NEW: startup/runtime error surfaced in the dashboard
    runtime: str = "docker"  # NEW: track which runtime (docker or native)


class VllmManager:
    def __init__(self) -> None:
        self.state = VllmState()
        self._proc: subprocess.Popen | None = None
        self._docker_bin = None
        self._public_fallback_image = "vllm/vllm-openai:latest"

    def _docker(self) -> str | None:
        if self._docker_bin is None:
            self._docker_bin = shutil.which("docker")
        return self._docker_bin

    def _fail(self, msg: str) -> VllmState:
        """Reset state to a clean startup-failure so the dashboard shows 'Échec'."""
        self.state = VllmState(
            running=False, error=msg, message=msg, runtime=self.state.runtime
        )
        return self.state

    @staticmethod
    def _resolve_tool_parser(model: str) -> str:
        """Pick the correct vLLM tool-call parser for a given model.

        --enable-auto-tool-choice REQUIRES a matching --tool-call-parser, otherwise
        vLLM aborts at startup (the container starts then exits immediately).
        """
        m = model.lower()
        if "phi-4" in m or "phi4" in m:
            return "phi4_mini_json"
        if "llama-3" in m or "llama3" in m or "llama-4" in m:
            return "llama3_json"
        if "qwen" in m:
            return "hermes"
        if "mistral" in m or "mixtral" in m:
            return "mistral"
        if "hermes" in m:
            return "hermes"
        if "gemma" in m:
            return "pythonic"
        # Safe generic default supported by most recent models
        return "hermes"

    def _tool_args(self, p: LaunchParams) -> list[str]:
        """Build tool-calling CLI args, auto-resolving the parser when needed."""
        if not p.enable_auto_tool_choice:
            return []
        parser = p.tool_call_parser.strip() or self._resolve_tool_parser(p.model)
        return ["--enable-auto-tool-choice", "--tool-call-parser", parser]

    @staticmethod
    def _servable_error(model_path: Path) -> str | None:
        """Return an error if a local model dir is NOT servable by vLLM.

        vLLM only serves text-generation models, which expose a HF ``config.json``
        (or a Mistral ``params.json``). Image->3D (TRELLIS.2, uses ``pipeline.json``)
        and text->image models have no such config and crash vLLM at startup with
        an opaque "Invalid repository ID or local directory" error. Catch this
        early and point the user to the Studio 3D page instead.
        """
        if (model_path / "config.json").exists() or (model_path / "params.json").exists():
            return None
        if (model_path / "pipeline.json").exists() or (model_path / "texturing_pipeline.json").exists():
            return (
                f"« {model_path.name} » est un modèle image→3D (TRELLIS.2) qui ne peut "
                "pas être servi par vLLM. Utilisez la page « Studio 3D » pour le charger."
            )
        return (
            f"« {model_path.name} » n'est pas servable par vLLM : aucun 'config.json' "
            "(ni 'params.json' Mistral) trouvé. Seuls les modèles de génération de "
            "texte sont pris en charge ici."
        )

    def _to_docker_args(self, p: LaunchParams) -> list[str]:
        """CLI args for Docker mode (model mounted as /models)."""
        served = p.served_model_name or p.model
        args = [
            "--model", "/models",
            "--served-model-name", served,
            "--host", "0.0.0.0",
            "--port", str(settings.vllm_port),
            "--dtype", p.dtype,
            "--max-model-len", str(p.max_model_len),
            "--gpu-memory-utilization", str(p.gpu_memory_utilization),
            "--tensor-parallel-size", str(p.tensor_parallel_size),
            "--max-num-seqs", str(p.max_num_seqs),
        ]
        if p.quantization:
            args += ["--quantization", p.quantization]
        if p.trust_remote_code:
            args += ["--trust-remote-code"]
        if p.enforce_eager:
            args += ["--enforce-eager"]
        args += self._tool_args(p)
        if p.extra_args.strip():
            args += p.extra_args.split()
        return args

    def _to_cli_args(self, p: LaunchParams) -> list[str]:
        """CLI args for native mode (model as HF repo or full path)."""
        served = p.served_model_name or p.model
        args = [
            "--model", str(p.model),
            "--served-model-name", served,
            "--host", "0.0.0.0",
            "--port", str(settings.vllm_port),
            "--dtype", p.dtype,
            "--max-model-len", str(p.max_model_len),
            "--gpu-memory-utilization", str(p.gpu_memory_utilization),
            "--tensor-parallel-size", str(p.tensor_parallel_size),
            "--max-num-seqs", str(p.max_num_seqs),
        ]
        if p.quantization:
            args += ["--quantization", p.quantization]
        if p.trust_remote_code:
            args += ["--trust-remote-code"]
        if p.enforce_eager:
            args += ["--enforce-eager"]
        args += self._tool_args(p)
        if p.extra_args.strip():
            args += p.extra_args.split()
        return args

    def _launch_docker(self, p: LaunchParams) -> VllmState:
        """Launch vLLM inside a Docker container."""
        docker = self._docker()
        if not docker:
            return self._fail("Docker introuvable.")

        model_path = settings.models_dir / p.model
        if not model_path.exists():
            return self._fail(
                f"Modèle non trouvé: {model_path}. Téléchargez-le d'abord."
            )

        servable_err = self._servable_error(model_path)
        if servable_err:
            return self._fail(servable_err)

        subprocess.run([docker, "rm", "-f", settings.vllm_container_name],
                      capture_output=True)

        def _build_cmd(image: str) -> list[str]:
            return [
                docker, "run", "-d",
                "--name", settings.vllm_container_name,
                "--gpus", "all",
                "--ipc=host",
                "-p", f"{settings.vllm_port}:{settings.vllm_port}",
                "-v", f"{model_path}:/models:ro",
                "-v", f"{Path.home() / '.cache' / 'huggingface'}:/root/.cache/huggingface",
                image,
                *self._to_docker_args(p),
            ]

        configured_image = settings.vllm_docker_image
        try:
            res = subprocess.run(_build_cmd(configured_image), 
                               capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                err = res.stderr.strip() or "Échec du lancement"
                # Fallback to public image if configured one fails
                should_fallback = (
                    configured_image != self._public_fallback_image
                    and any(x in err.lower() for x in ["not found", "access denied", "denied"])
                )
                if should_fallback:
                    res_fb = subprocess.run(_build_cmd(self._public_fallback_image),
                                          capture_output=True, text=True, timeout=120)
                    if res_fb.returncode != 0:
                        return self._fail(
                            f"Image {configured_image} indisponible | "
                            f"fallback {self._public_fallback_image} échoué"
                        )
                    return VllmState(
                        running=True,
                        model=p.served_model_name or p.model,
                        params={**p.__dict__, "docker_image": self._public_fallback_image},
                        container_id=res_fb.stdout.strip()[:12],
                        message=f"Fallback {self._public_fallback_image}. Démarrage…",
                        runtime="docker",
                    )
                return self._fail(err)
            container_id = res.stdout.strip()[:12]
            # Detect an immediate crash (e.g. bad tool-call-parser) and surface logs.
            early = self._check_early_exit(docker, container_id)
            if early is not None:
                self.state = VllmState(
                    running=False,
                    model=p.served_model_name or p.model,
                    params={**p.__dict__, "docker_image": configured_image},
                    container_id=container_id,
                    message=f"Le conteneur vLLM s'est arrêté au démarrage : {early}",
                    error=early,
                    runtime="docker",
                )
                return self.state
            self.state = VllmState(
                running=True,
                model=p.served_model_name or p.model,
                params={**p.__dict__, "docker_image": configured_image},
                container_id=container_id,
                message="vLLM Docker en démarrage…",
                runtime="docker",
            )
        except Exception as exc:
            return self._fail(str(exc))
        return self.state

    def _check_early_exit(self, docker: str, container_id: str) -> str | None:
        """Return a short error from container logs if it exited shortly after start.

        Returns None if the container is still running (normal model loading).
        """
        time.sleep(3)
        try:
            insp = subprocess.run(
                [docker, "inspect", "-f", "{{.State.Running}}", container_id],
                capture_output=True, text=True, timeout=10,
            )
            if insp.stdout.strip() == "true":
                return None  # still running, loading normally
            logs = subprocess.run(
                [docker, "logs", "--tail", "30", container_id],
                capture_output=True, text=True, timeout=10,
            )
            output = (logs.stderr or "") + (logs.stdout or "")
            lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
            tail = " | ".join(lines[-5:]) if lines else "logs indisponibles"
            return tail[:500]
        except Exception:
            return None

    def _launch_native(self, p: LaunchParams) -> VllmState:
        """Launch vLLM natively as a subprocess (requires pip install vllm)."""
        try:
            import vllm  # noqa: F401
        except ImportError:
            return self._fail(
                "vLLM n'est pas installé. Installez via: pip install vllm"
            )

        # Stop any previous native process
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            time.sleep(1)

        # Reject non-LLM local models (e.g. TRELLIS.2 image->3D) before starting.
        local_path = settings.models_dir / p.model
        if local_path.exists() and local_path.is_dir():
            servable_err = self._servable_error(local_path)
            if servable_err:
                return self._fail(servable_err)

        cmd = [
            sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            *self._to_cli_args(p),
        ]
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True)
            self.state = VllmState(
                running=True,
                model=p.served_model_name or p.model,
                params=p.__dict__,
                container_id=str(self._proc.pid),
                message="vLLM natif en démarrage…",
                runtime="native",
            )
        except Exception as exc:
            return self._fail(str(exc))
        return self.state

    def launch(self, p: LaunchParams) -> VllmState:
        """Launch vLLM using the specified runtime (docker or native)."""
        # Clear any previous startup error before a fresh attempt.
        self.state.error = ""
        if p.runtime == "native":
            return self._launch_native(p)
        else:
            return self._launch_docker(p)

    def _detect_failure(self) -> str | None:
        """Return an error string if a *running* vLLM has actually crashed.

        Used during the loading phase (before /health is ready) to catch a
        container/process that died mid-startup and surface its logs.
        """
        if self.state.runtime == "native":
            if self._proc is not None and self._proc.poll() is not None:
                code = self._proc.returncode
                err = ""
                try:
                    if self._proc.stderr:
                        err = self._proc.stderr.read() or ""
                except Exception:
                    err = ""
                lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
                tail = " | ".join(lines[-8:])[-800:]
                return tail or f"Processus vLLM terminé (code {code})."
            return None

        # Docker runtime
        docker = self._docker()
        cid = self.state.container_id
        if not docker or not cid:
            return None
        try:
            insp = subprocess.run(
                [docker, "inspect", "-f", "{{.State.Status}}", cid],
                capture_output=True, text=True, timeout=10,
            )
            if insp.returncode != 0:
                return "Conteneur vLLM introuvable (arrêté au démarrage)."
            st = insp.stdout.strip()
            if st in ("running", "created", "restarting"):
                return None  # still loading normally
            logs = subprocess.run(
                [docker, "logs", "--tail", "40", cid],
                capture_output=True, text=True, timeout=10,
            )
            output = (logs.stderr or "") + (logs.stdout or "")
            lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
            tail = " | ".join(lines[-8:]) if lines else f"Conteneur arrêté (état {st})."
            return tail[:800]
        except Exception:
            return None

    def stop(self) -> VllmState:
        """Stop vLLM (Docker or native subprocess)."""
        docker = self._docker()
        if docker:
            subprocess.run([docker, "rm", "-f", settings.vllm_container_name],
                          capture_output=True)
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._proc = None
        self.state = VllmState(running=False, message="vLLM arrêté.", runtime=self.state.runtime)
        return self.state

    async def health(self) -> dict[str, Any]:
        """Check vLLM health (both runtimes)."""
        url = f"http://{settings.vllm_host}:{settings.vllm_port}/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
                ready = r.status_code == 200
        except Exception:
            ready = False

        # If native proc exited, mark as not running
        if self.state.runtime == "native" and self._proc and self._proc.poll() is not None:
            self.state.running = False

        # Detect a crash during the loading phase and surface the logs so the
        # dashboard can show "Échec" with the error message.
        if self.state.running and not ready:
            err = self._detect_failure()
            if err:
                self.state.running = False
                self.state.error = err
                self.state.message = f"Échec du démarrage de vLLM : {err}"

        if self.state.error and not self.state.running:
            status = "failed"
        elif self.state.running and ready:
            status = "ready"
        elif self.state.running:
            status = "loading"
        else:
            status = "stopped"

        return {
            "running": self.state.running,
            "ready": ready,
            "status": status,
            "error": self.state.error,
            "model": self.state.model,
            "runtime": self.state.runtime,
            "params": self.state.params,
            "message": self.state.message,
        }


vllm_manager = VllmManager()
