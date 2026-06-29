"""Ollama lifecycle + model management for the offline GitHub Copilot backend.

Ollama runs in the ``dgx-demo-ollama`` container (see ``docker-compose.yml``)
and exposes an OpenAI-compatible API on :11434 that the GitHub Copilot CLI and
VS Code chat talk to in offline / airgapped mode.

This manager:
  * reports the container + endpoint status (version, loaded models),
  * lists / deletes models stored in the Ollama volume,
  * pulls models (streaming progress straight from Ollama's ``/api/pull``),
  * starts / stops the container via ``docker compose``.

Everything is local: no traffic ever leaves the host.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from app.config import settings


# Public Ollama model library — used for the in-UI model search. Ollama's local
# server has no registry-search endpoint, so search queries ollama.com directly
# (pulling a new model needs network anyway). Stable ``x-test-*`` markers in the
# page make the parse resilient; failures degrade to an empty list.
OLLAMA_LIBRARY = "https://ollama.com"


def _clean(text: str) -> str:
    return html.unescape(text).strip()


@dataclass
class OllamaStatus:
    container_running: bool = False
    endpoint_up: bool = False
    version: str = ""
    base_url: str = ""
    openai_url: str = ""
    models: list[dict[str, Any]] | None = None
    loaded: list[dict[str, Any]] | None = None
    message: str = ""


class OllamaManager:
    def __init__(self) -> None:
        self._docker_bin: str | None = None

    # ------------------------------------------------------------------ docker
    def _docker(self) -> str | None:
        if self._docker_bin is None:
            self._docker_bin = shutil.which("docker")
        return self._docker_bin

    def _compose(self, *args: str) -> subprocess.CompletedProcess:
        docker = self._docker()
        if not docker:
            raise RuntimeError("docker binary not found on PATH")
        cmd = [docker, "compose", "-f",
               str(settings.repo_root / "docker-compose.yml"), *args]
        return subprocess.run(
            cmd, cwd=str(settings.repo_root),
            capture_output=True, text=True, timeout=180,
        )

    def container_running(self) -> bool:
        docker = self._docker()
        if not docker:
            return False
        try:
            res = subprocess.run(
                [docker, "ps", "--filter",
                 f"name={settings.ollama_container_name}",
                 "--filter", "status=running",
                 "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
            return settings.ollama_container_name in res.stdout
        except Exception:
            return False

    def start_container(self) -> dict[str, Any]:
        try:
            res = self._compose("up", "-d", "ollama")
            ok = res.returncode == 0
            return {"ok": ok, "message": (res.stderr or res.stdout).strip()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}

    def stop_container(self) -> dict[str, Any]:
        try:
            res = self._compose("stop", "ollama")
            ok = res.returncode == 0
            return {"ok": ok, "message": (res.stderr or res.stdout).strip()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}

    # ------------------------------------------------------------------- http
    async def _get(self, path: str, timeout: float = 5.0) -> Any:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{settings.ollama_base_url}{path}")
            r.raise_for_status()
            return r.json()

    async def version(self) -> str:
        try:
            data = await self._get("/api/version")
            return str(data.get("version", ""))
        except Exception:
            return ""

    async def list_models(self) -> list[dict[str, Any]]:
        """Models present in the local Ollama volume (``/api/tags``)."""
        try:
            data = await self._get("/api/tags")
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        for m in data.get("models", []) or []:
            details = m.get("details", {}) or {}
            out.append({
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "modified_at": m.get("modified_at", ""),
                "family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
            })
        out.sort(key=lambda x: x["name"])
        return out

    async def loaded_models(self) -> list[dict[str, Any]]:
        """Models currently resident in memory (``/api/ps``)."""
        try:
            data = await self._get("/api/ps")
        except Exception:
            return []
        return [
            {
                "name": m.get("name", ""),
                "size_vram": m.get("size_vram", 0),
                "expires_at": m.get("expires_at", ""),
            }
            for m in data.get("models", []) or []
        ]

    async def status(self) -> dict[str, Any]:
        st = OllamaStatus(
            base_url=settings.ollama_base_url,
            openai_url=settings.ollama_openai_url,
        )
        st.container_running = self.container_running()
        st.version = await self.version()
        st.endpoint_up = bool(st.version)
        if st.endpoint_up:
            st.models = await self.list_models()
            st.loaded = await self.loaded_models()
        else:
            st.models = []
            st.loaded = []
            st.message = (
                "Ollama endpoint unreachable. Start the container from this "
                "page or run: docker compose up -d ollama"
            )
        return st.__dict__

    async def delete_model(self, name: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.request(
                    "DELETE", f"{settings.ollama_base_url}/api/delete",
                    json={"name": name},
                )
            ok = r.status_code == 200
            return {"ok": ok, "message": "" if ok else r.text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}

    async def pull_stream(self, name: str) -> AsyncIterator[str]:
        """Stream NDJSON pull-progress lines straight from Ollama.

        Each yielded chunk is a JSON line such as
        ``{"status": "pulling ...", "completed": N, "total": M}`` finishing with
        ``{"status": "success"}``. The endpoint forwards these to the browser.
        """
        payload = {"name": name, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", f"{settings.ollama_base_url}/api/pull",
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "ignore")
                        yield json.dumps({"status": "error",
                                          "error": body or resp.reason_phrase})
                        return
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield line
        except Exception as exc:  # noqa: BLE001
            yield json.dumps({"status": "error", "error": str(exc)})

    async def load_model(self, name: str) -> dict[str, Any]:
        """Load a local model into memory (``/api/generate`` with no prompt).

        Ollama loads the weights and returns immediately; the model then stays
        resident per ``OLLAMA_KEEP_ALIVE``. This is the "Run" action in the UI.
        """
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/generate",
                    json={"model": name, "keep_alive": "30m"},
                )
            ok = r.status_code == 200
            return {"ok": ok, "message": "" if ok else r.text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}

    async def stop_model(self, name: str) -> dict[str, Any]:
        """Unload a running model from memory (``keep_alive=0``).

        Ollama keeps models resident per ``OLLAMA_KEEP_ALIVE``; sending an empty
        ``/api/generate`` with ``keep_alive=0`` evicts it immediately, freeing
        VRAM. This is the "Stop" action in the UI.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/generate",
                    json={"model": name, "keep_alive": 0},
                )
            ok = r.status_code == 200
            return {"ok": ok, "message": "" if ok else r.text}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}

    async def model_info(self, name: str) -> dict[str, Any]:
        """Capabilities + chat template for a local model (``/api/show``).

        ``capabilities`` tells you whether the model advertises ``tools``,
        ``vision``, ``thinking`` etc. The ``template`` is the exact Jinja the
        model was fine-tuned on — for tool-capable models it shows how Ollama
        injects the offered tools and how the model wraps a ``tool_calls``
        response. Note: advertising ``tools`` means *trained for* tool use, not
        that every call will be schema-valid (see the offline tool test).
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/show",
                    json={"name": name},
                )
            if r.status_code != 200:
                return {"ok": False, "message": r.text, "name": name}
            data = r.json()
            details = data.get("details", {}) or {}
            return {
                "ok": True,
                "name": name,
                "capabilities": data.get("capabilities", []) or [],
                "supports_tools": "tools" in (data.get("capabilities") or []),
                "template": data.get("template", "") or "",
                "system": data.get("system", "") or "",
                "parameters": data.get("parameters", "") or "",
                "family": details.get("family", ""),
                "parameter_size": details.get("parameter_size", ""),
                "quantization_level": details.get("quantization_level", ""),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc), "name": name}

    async def search_library(self, query: str, limit: int = 24) \
            -> list[dict[str, Any]]:
        """Search the public Ollama library (ollama.com) for models."""
        try:
            async with httpx.AsyncClient(timeout=15.0,
                                         follow_redirects=True) as client:
                r = await client.get(f"{OLLAMA_LIBRARY}/search",
                                     params={"q": query})
                r.raise_for_status()
                page = r.text
        except Exception:  # noqa: BLE001
            return []

        results: list[dict[str, Any]] = []
        # Each model card starts with the title marker; split on it and parse
        # the markers that follow within the same card.
        blocks = re.split(r"x-test-search-response-title>", page)[1:]
        for block in blocks[:limit]:
            name_m = re.match(r"([^<]+)", block)
            if not name_m:
                continue
            name = _clean(name_m.group(1))
            desc_m = re.search(
                r'text-neutral-800 text-md">\s*([^<]+)', block)
            pulls_m = re.search(r"x-test-pull-count>([^<]+)", block)
            caps = [_clean(c) for c in
                    re.findall(r"x-test-capability>([^<]+)", block)]
            sizes = [_clean(s) for s in
                     re.findall(r"x-test-size>([^<]+)", block)]
            results.append({
                "name": name,
                "description": _clean(desc_m.group(1)) if desc_m else "",
                "pulls": _clean(pulls_m.group(1)) if pulls_m else "",
                "capabilities": caps,
                "sizes": sizes,
            })
        return results

    async def library_tags(self, name: str, limit: int = 40) \
            -> list[dict[str, Any]]:
        """List the available tags (+ sizes) for a model on ollama.com."""
        try:
            async with httpx.AsyncClient(timeout=15.0,
                                         follow_redirects=True) as client:
                r = await client.get(f"{OLLAMA_LIBRARY}/library/{name}/tags")
                r.raise_for_status()
                page = r.text
        except Exception:  # noqa: BLE001
            return []

        seen: dict[str, str] = {}
        blocks = re.split(
            r'href="/library/' + re.escape(name) + r":", page)[1:]
        for block in blocks:
            tag_m = re.match(r"([a-zA-Z0-9._-]+)\"", block)
            if not tag_m:
                continue
            tag = tag_m.group(1)
            size_m = re.search(r"([0-9.]+\s?[KMGT]B)", block)
            size = size_m.group(1) if size_m else ""
            if tag not in seen or (not seen[tag] and size):
                seen[tag] = size
        return [{"tag": t, "size": s, "full": f"{name}:{t}"}
                for t, s in list(seen.items())[:limit]]


ollama_manager = OllamaManager()
