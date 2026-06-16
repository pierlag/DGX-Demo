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
            self.state.message = "Docker introuvable."
            return self.state

        model_path = settings.models_dir / p.model
        if not model_path.exists():
            self.state.message = f"Modèle non trouvé: {model_path}. Téléchargez-le d'abord."
            return self.state

        subprocess.run([docker, "rm", "-f", settings.vllm_container_name],
                      capture_output=True)

        def _build_cmd(image: str) -> list[str]:
            return [
                docker, "run", "-d", "--rm",
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
                        self.state.message = (
                            f"Image {configured_image} indisponible | "
                            f"fallback {self._public_fallback_image} échoué"
                        )
                        return self.state
                    return VllmState(
                        running=True,
                        model=p.served_model_name or p.model,
                        params={**p.__dict__, "docker_image": self._public_fallback_image},
                        container_id=res_fb.stdout.strip()[:12],
                        message=f"Fallback {self._public_fallback_image}. Démarrage…",
                        runtime="docker",
                    )
                self.state.message = err
                return self.state
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
            self.state.message = str(exc)
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
            self.state.message = (
                "vLLM n'est pas installé. Installez via: pip install vllm"
            )
            return self.state

        # Stop any previous native process
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            time.sleep(1)

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
            self.state.message = str(exc)
        return self.state

    def launch(self, p: LaunchParams) -> VllmState:
        """Launch vLLM using the specified runtime (docker or native)."""
        if p.runtime == "native":
            return self._launch_native(p)
        else:
            return self._launch_docker(p)

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

        return {
            "running": self.state.running,
            "ready": ready,
            "model": self.state.model,
            "runtime": self.state.runtime,
            "params": self.state.params,
            "message": self.state.message,
        }


vllm_manager = VllmManager()
