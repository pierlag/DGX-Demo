"""GitHub Copilot CLI / VS Code chat — offline (airgapped) BYOK integration.

The DGX Demo already runs a local **vLLM** server that is OpenAI-compatible
(``/v1``). This module wires the GitHub Copilot CLI (and VS Code chat) to that
local server in **offline mode**, so the agent talks only to the on-device model
and never to GitHub's servers — the BYOK + ``COPILOT_OFFLINE=true`` pattern from
https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models#running-in-offline-mode

It exposes:
  * ``status()``            — readiness (vLLM reachable, served model, CLI/VS Code present)
  * ``run_validation()``    — a BYOK test-suite against vLLM (models / chat / stream / tools)
  * ``cli_env()``           — the ``COPILOT_PROVIDER_*`` environment for the CLI
  * ``vscode_config()``     — the OpenAI-compatible provider fields for VS Code chat
  * ``write_launch_script()`` — generate ``scripts/start-copilot-offline.sh``

Every validation turn is recorded into the shared ``metrics_store`` so the
dashboard + Grafana "Copilot CLI activity" panels light up.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx

from app.config import settings
from app.services.metrics import metrics_store

# The Copilot CLI does NOT auto-append "/v1": the base URL must already include
# it. ``settings.vllm_base_url`` already ends with ``/v1``.
_BASE_URL = settings.vllm_base_url
_DUMMY_KEY = "vllm"  # local vLLM needs no auth; the CLI still requires a value


class CopilotManager:
    """Wires the offline Copilot CLI / VS Code chat to the local vLLM server."""

    def __init__(self) -> None:
        self._copilot_bin: str | None = None
        self._code_bin: str | None = None

    # ------------------------------------------------------------------ bins
    def _which(self, name: str, cache_attr: str) -> str | None:
        cached = getattr(self, cache_attr)
        if cached is None:
            cached = shutil.which(name) or ""
            setattr(self, cache_attr, cached)
        return cached or None

    def _bin_version(self, binary: str | None) -> str:
        if not binary:
            return ""
        try:
            res = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=8
            )
            return (res.stdout or res.stderr).strip().splitlines()[0] if (
                res.stdout or res.stderr
            ) else ""
        except Exception:
            return ""

    # ------------------------------------------------------------- vLLM probe
    async def _served_model(self) -> str | None:
        """Return the model id served by vLLM (source of truth for BYOK)."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.get(f"{_BASE_URL}/models")
                r.raise_for_status()
                data = r.json().get("data", [])
                if data:
                    return data[0].get("id")
        except Exception:
            return None
        return None

    # --------------------------------------------------------------- status
    async def status(self) -> dict:
        copilot_bin = self._which("copilot", "_copilot_bin")
        code_bin = self._which("code", "_code_bin")
        model = await self._served_model()
        return {
            "base_url": _BASE_URL,
            "offline": True,
            "vllm_up": model is not None,
            "model": model or "",
            "copilot_installed": bool(copilot_bin),
            "copilot_version": self._bin_version(copilot_bin),
            "vscode_installed": bool(code_bin),
            "vscode_version": self._bin_version(code_bin),
            "session_active": metrics_store.copilot_session_active,
        }

    # ----------------------------------------------------------- validation
    async def run_validation(self) -> dict:
        """Run the BYOK validation suite against the local vLLM server.

        The agentic Copilot CLI needs a model that supports **streaming** and
        returns **structured ``tool_calls``** (not tool calls as plain text), so
        the suite checks: the OpenAI-compatible ``/models`` route, a non-stream
        chat completion, a streaming completion, and a tool-calling completion.
        """
        model = await self._served_model()
        results: list[dict] = []

        async with httpx.AsyncClient(timeout=120.0) as client:
            results.append(await self._test_models(client))

            if not model:
                for name in ("chat", "stream", "tools"):
                    results.append({
                        "test": name, "ok": False, "latency_ms": 0.0,
                        "detail": "vLLM not running — launch a model first.",
                    })
            else:
                results.append(await self._test_chat(client, model))
                results.append(await self._test_stream(client, model))
                results.append(await self._test_tools(client, model))

        for r in results:
            metrics_store.record_copilot(
                test=r["test"], ok=r["ok"], latency_ms=r["latency_ms"],
                detail=r["detail"],
                tool_calls=1 if (r["test"] == "tools" and r["ok"]) else 0,
            )

        passed = sum(1 for r in results if r["ok"])
        return {
            "model": model or "",
            "passed": passed,
            "total": len(results),
            "ok": passed == len(results),
            "results": results,
        }

    async def _test_models(self, client: httpx.AsyncClient) -> dict:
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{_BASE_URL}/models")
            r.raise_for_status()
            ids = [m.get("id") for m in r.json().get("data", [])]
            ok = bool(ids)
            detail = f"served: {', '.join(i for i in ids if i)}" if ok else "no models"
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        return self._result("models", ok, t0, detail)

    async def _test_chat(self, client: httpx.AsyncClient, model: str) -> dict:
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{_BASE_URL}/chat/completions", json={
                "model": model, "stream": False, "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            })
            r.raise_for_status()
            content = (r.json()["choices"][0]["message"].get("content") or "").strip()
            ok = bool(content)
            detail = f"reply: {content[:60]}" if ok else "empty completion"
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        return self._result("chat", ok, t0, detail)

    async def _test_stream(self, client: httpx.AsyncClient, model: str) -> dict:
        t0 = time.perf_counter()
        chunks = 0
        try:
            async with client.stream("POST", f"{_BASE_URL}/chat/completions", json={
                "model": model, "stream": True, "max_tokens": 16,
                "messages": [{"role": "user", "content": "Count: 1 2 3"}],
            }) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if line.startswith("data:") and "[DONE]" not in line:
                        chunks += 1
            ok = chunks > 0
            detail = f"{chunks} stream chunks" if ok else "no stream chunks"
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        return self._result("stream", ok, t0, detail)

    async def _test_tools(self, client: httpx.AsyncClient, model: str) -> dict:
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{_BASE_URL}/chat/completions", json={
                "model": model, "stream": False, "max_tokens": 128,
                "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the weather for a city",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                }],
            })
            r.raise_for_status()
            tool_calls = r.json()["choices"][0]["message"].get("tool_calls")
            ok = bool(tool_calls)
            if ok:
                fn = tool_calls[0].get("function", {}).get("name", "?")
                detail = f"structured tool_calls → {fn}()"
            else:
                detail = (
                    "no structured tool_calls — launch vLLM with "
                    "--enable-auto-tool-choice + a matching --tool-call-parser."
                )
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"{type(e).__name__}: {e}"
        return self._result("tools", ok, t0, detail)

    @staticmethod
    def _result(test: str, ok: bool, t0: float, detail: str) -> dict:
        return {
            "test": test,
            "ok": ok,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "detail": detail,
        }

    # ------------------------------------------------------------ config out
    def cli_env(self, model: str) -> dict[str, str]:
        """Environment variables that wire the Copilot CLI to vLLM, offline."""
        return {
            "COPILOT_PROVIDER_TYPE": "openai",
            "COPILOT_PROVIDER_BASE_URL": _BASE_URL,  # must include /v1
            "COPILOT_PROVIDER_API_KEY": _DUMMY_KEY,
            "COPILOT_MODEL": model or "<served-model-id>",
            "COPILOT_OFFLINE": "true",
        }

    def vscode_config(self, model: str) -> dict:
        """OpenAI-compatible provider fields for the VS Code chat BYOK dialog.

        In VS Code: *Chat → Manage Models → Add → OpenAI Compatible*, then enter
        these values. The settings snippet mirrors the same provider for
        ``.vscode/settings.json``.
        """
        settings_snippet = {
            "github.copilot.chat.byok.openAICompatible": {
                "baseUrl": _BASE_URL,
                "apiKey": _DUMMY_KEY,
                "models": [model or "<served-model-id>"],
            }
        }
        return {
            "provider": "OpenAI Compatible",
            "base_url": _BASE_URL,
            "api_key": _DUMMY_KEY,
            "model": model or "<served-model-id>",
            "settings_json": json.dumps(settings_snippet, indent=2),
        }

    # ----------------------------------------------------- launch script gen
    def write_launch_script(self, model: str) -> dict:
        """Generate ``scripts/start-copilot-offline.sh`` wired to vLLM."""
        script = settings.repo_root / "scripts" / "start-copilot-offline.sh"
        env = self.cli_env(model)
        body = f"""#!/usr/bin/env bash
# start-copilot-offline.sh  (generated by the DGX Demo dashboard)
# Wires the GitHub Copilot CLI to the local vLLM server in offline / airgapped
# mode, so the agent talks only to the on-device model. Re-generate from the
# dashboard "Copilot CLI" page to refresh the served model id.
set -euo pipefail

BASE_URL="{env['COPILOT_PROVIDER_BASE_URL']}"

echo "==> Checking the local vLLM server at ${{BASE_URL}}/models ..."
if ! curl -fsS --max-time 5 "${{BASE_URL}}/models" >/dev/null 2>&1; then
  echo "ERROR: vLLM is not reachable at ${{BASE_URL}}." >&2
  echo "       Launch a model from the dashboard (Models vLLM) first." >&2
  exit 1
fi

command -v copilot >/dev/null 2>&1 || {{
  echo "ERROR: 'copilot' CLI not found. Install: npm install -g @github/copilot" >&2
  exit 1
}}

export COPILOT_PROVIDER_TYPE="{env['COPILOT_PROVIDER_TYPE']}"
export COPILOT_PROVIDER_BASE_URL="${{BASE_URL}}"
export COPILOT_PROVIDER_API_KEY="{env['COPILOT_PROVIDER_API_KEY']}"
export COPILOT_MODEL="{env['COPILOT_MODEL']}"
export COPILOT_OFFLINE="true"

echo "  COPILOT_PROVIDER_BASE_URL = ${{COPILOT_PROVIDER_BASE_URL}}"
echo "  COPILOT_MODEL             = ${{COPILOT_MODEL}}"
echo "  COPILOT_OFFLINE           = true"
echo

exec copilot "$@"
"""
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(body, encoding="utf-8")
        try:
            script.chmod(0o755)
        except Exception:
            pass
        return {"path": str(script), "model": model or ""}


copilot_manager = CopilotManager()
