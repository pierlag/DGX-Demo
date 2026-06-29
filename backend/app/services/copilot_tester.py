"""Offline GitHub Copilot integration tests + helpers.

The GitHub Copilot CLI and VS Code chat can run fully offline by pointing their
provider at the local Ollama OpenAI-compatible endpoint (the
``COPILOT_PROVIDER_*`` environment variables). For the *agentic* CLI to work the
served model must:

  1. be advertised on the OpenAI ``/v1/models`` route,
  2. answer a basic chat completion,
  3. stream with a ``finish_reason`` (Copilot's stream parser needs it),
  4. return **structured** ``tool_calls`` (not tool calls as plain text).

``run_tests`` exercises all four against the local endpoint and returns a
pass/fail report the dashboard renders. ``cli_status`` detects the installed
tooling and ``env_block`` / ``vscode_settings`` produce copy-ready launch config.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

import httpx

from app.config import settings


def _which_version(binary: str, *version_args: str) -> dict[str, Any]:
    path = shutil.which(binary)
    if not path:
        return {"installed": False, "path": "", "version": ""}
    version = ""
    try:
        res = subprocess.run(
            [binary, *(version_args or ("--version",))],
            capture_output=True, text=True, timeout=10,
        )
        version = (res.stdout or res.stderr).strip().splitlines()[0] \
            if (res.stdout or res.stderr).strip() else ""
    except Exception:  # noqa: BLE001
        version = ""
    return {"installed": True, "path": path, "version": version}


class CopilotTester:
    # -------------------------------------------------------------- tooling
    def cli_status(self) -> dict[str, Any]:
        """Detect the offline Copilot tooling installed on the host."""
        copilot = _which_version("copilot", "--version")
        code = _which_version("code", "--version")

        chat_ext = False
        if code["installed"]:
            try:
                res = subprocess.run(
                    ["code", "--list-extensions"],
                    capture_output=True, text=True, timeout=15,
                )
                exts = res.stdout.lower()
                chat_ext = "github.copilot-chat" in exts
            except Exception:  # noqa: BLE001
                chat_ext = False

        return {
            "copilot_cli": copilot,
            "vscode": code,
            "vscode_copilot_chat": chat_ext,
        }

    async def _models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{settings.ollama_openai_url}/models")
                r.raise_for_status()
                data = r.json()
            return [m.get("id", "") for m in data.get("data", []) or []]
        except Exception:  # noqa: BLE001
            return []

    async def resolve_model(self, model: str | None) -> str:
        """Use the requested model, else the first model present in Ollama."""
        if model:
            return model
        ids = await self._models()
        return ids[0] if ids else ""

    # ---------------------------------------------------------------- checks
    async def run_tests(self, model: str | None = None) -> dict[str, Any]:
        base = settings.ollama_openai_url
        resolved = await self.resolve_model(model)
        checks: list[dict[str, Any]] = []

        if not resolved:
            return {
                "model": "",
                "base_url": base,
                "ok": False,
                "checks": [{
                    "name": "models",
                    "status": "fail",
                    "detail": "No model available. Pull one first "
                              "(e.g. llama3.2:3b) from the Models section above.",
                    "duration_ms": 0,
                }],
            }

        checks.append(await self._check_models(resolved))
        checks.append(await self._check_chat(base, resolved))
        checks.append(await self._check_stream(base, resolved))
        checks.append(await self._check_tools(base, resolved))

        ok = all(c["status"] == "pass" for c in checks)
        return {"model": resolved, "base_url": base, "ok": ok, "checks": checks}

    async def _check_models(self, model: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        ids = await self._models()
        dur = int((time.perf_counter() - t0) * 1000)
        if model in ids:
            return {"name": "models", "status": "pass",
                    "detail": f"/v1/models lists '{model}' ({len(ids)} total).",
                    "duration_ms": dur}
        if ids:
            return {"name": "models", "status": "warn",
                    "detail": f"'{model}' not in /v1/models, but {len(ids)} "
                              f"model(s) available: {', '.join(ids[:5])}.",
                    "duration_ms": dur}
        return {"name": "models", "status": "fail",
                "detail": "OpenAI /v1/models route returned nothing. Is Ollama "
                          "running and a model pulled?",
                "duration_ms": dur}

    async def _check_chat(self, base: str, model: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        payload = {
            "model": model,
            "stream": False,
            "messages": [{
                "role": "user",
                "content": "Reply with exactly the single word PONG.",
            }],
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{base}/chat/completions", json=payload)
                r.raise_for_status()
                data = r.json()
            content = (data["choices"][0]["message"].get("content") or "").strip()
            dur = int((time.perf_counter() - t0) * 1000)
            if "pong" in content.lower():
                return {"name": "chat", "status": "pass",
                        "detail": f"Model replied: '{content[:60]}'.",
                        "duration_ms": dur}
            return {"name": "chat", "status": "warn",
                    "detail": f"Chat works but off-task reply: '{content[:60]}'.",
                    "duration_ms": dur}
        except Exception as exc:  # noqa: BLE001
            dur = int((time.perf_counter() - t0) * 1000)
            return {"name": "chat", "status": "fail",
                    "detail": f"Chat completion failed: {exc}",
                    "duration_ms": dur}

    async def _check_stream(self, base: str, model: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        payload = {
            "model": model,
            "stream": True,
            "messages": [{"role": "user", "content": "Say hi in one word."}],
        }
        try:
            saw_finish = False
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST", f"{base}/chat/completions", json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        chunk = line[len("data:"):].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            obj = json.loads(chunk)
                        except Exception:  # noqa: BLE001
                            continue
                        fr = obj.get("choices", [{}])[0].get("finish_reason")
                        if fr:
                            saw_finish = True
            dur = int((time.perf_counter() - t0) * 1000)
            if saw_finish:
                return {"name": "stream", "status": "pass",
                        "detail": "SSE stream carried a finish_reason.",
                        "duration_ms": dur}
            return {"name": "stream", "status": "fail",
                    "detail": "No finish_reason in the stream — Copilot's stream "
                              "parser would hang.",
                    "duration_ms": dur}
        except Exception as exc:  # noqa: BLE001
            dur = int((time.perf_counter() - t0) * 1000)
            return {"name": "stream", "status": "fail",
                    "detail": f"Streaming request failed: {exc}",
                    "duration_ms": dur}

    async def _check_tools(self, base: str, model: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        payload = {
            "model": model,
            "stream": False,
            "messages": [{
                "role": "user",
                "content": "What is the weather in Paris? Use the tool.",
            }],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }],
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{base}/chat/completions", json=payload)
                r.raise_for_status()
                data = r.json()
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            content = msg.get("content") or ""
            dur = int((time.perf_counter() - t0) * 1000)
            if tool_calls:
                # Having *some* tool_calls is not enough: the agentic CLI rejects
                # calls whose name is hallucinated or whose arguments don't match
                # the schema (e.g. gpt-oss -> "400 invalid tool call arguments").
                # Validate name == get_weather and arguments = {city: <string>}.
                name_ok = False
                args_ok = False
                bad = ""
                for tc in tool_calls:
                    fn = tc.get("function", {}) or {}
                    if fn.get("name") == "get_weather":
                        name_ok = True
                    raw = fn.get("arguments")
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) \
                            else (raw or {})
                    except Exception:  # noqa: BLE001
                        parsed = None
                        bad = bad or f"arguments are not valid JSON: {raw!r}"
                    if isinstance(parsed, dict) and \
                            isinstance(parsed.get("city"), str) and \
                            parsed["city"].strip():
                        args_ok = True
                    elif parsed is not None and not bad:
                        bad = f"arguments don't match the schema: {raw!r}"
                if name_ok and args_ok:
                    return {"name": "tools", "status": "pass",
                            "detail": f"Schema-conformant tool_calls returned "
                                      f"(n={len(tool_calls)}). Agentic CLI "
                                      f"supported.",
                            "duration_ms": dur}
                if not name_ok:
                    return {"name": "tools", "status": "warn",
                            "detail": "Returns tool_calls but with a function "
                                      "name that doesn't match the offered tool "
                                      "(hallucinated tool). The agentic CLI will "
                                      "error with \"Tool '...' does not exist\". "
                                      "Use a stronger tool-trained model.",
                            "duration_ms": dur}
                return {"name": "tools", "status": "warn",
                        "detail": "Returns tool_calls but the arguments are "
                                  f"malformed ({bad}). The agentic CLI rejects "
                                  "these as \"400 invalid tool call arguments\" "
                                  "(typical of gpt-oss / reasoning models). Use a "
                                  "model like llama3.1:8b, qwen2.5:7b or "
                                  "mistral:7b for agentic work.",
                        "duration_ms": dur}
            if "get_weather" in content:
                return {"name": "tools", "status": "fail",
                        "detail": "Emits the tool call as TEXT in content — the "
                                  "agent loop cannot parse it. Pick a model with "
                                  "structured tool calls.",
                        "duration_ms": dur}
            return {"name": "tools", "status": "fail",
                    "detail": "No tool_calls returned. This model can't drive the "
                              "agentic Copilot CLI (chat still works).",
                    "duration_ms": dur}
        except Exception as exc:  # noqa: BLE001
            dur = int((time.perf_counter() - t0) * 1000)
            return {"name": "tools", "status": "fail",
                    "detail": f"Tool-calling request failed: {exc}",
                    "duration_ms": dur}

    # -------------------------------------------------------------- helpers
    def env_block(self, model: str) -> dict[str, str]:
        """The COPILOT_PROVIDER_* environment for the offline CLI."""
        return {
            "COPILOT_PROVIDER_TYPE": "openai",
            "COPILOT_PROVIDER_BASE_URL": settings.ollama_openai_url,
            "COPILOT_PROVIDER_API_KEY": "ollama",
            "COPILOT_MODEL": model,
            "COPILOT_OFFLINE": "true",
        }

    def vscode_settings(self, model: str) -> dict[str, Any]:
        """settings.json snippet pointing VS Code chat at local Ollama."""
        return {
            "github.copilot.chat.byok.ollamaEndpoint": settings.ollama_base_url,
            "github.copilot.advanced": {"debug.useElectronFetcher": False},
            "_note": (
                "VS Code chat: open the model picker > 'Manage Models' > "
                f"'Ollama', set the endpoint to {settings.ollama_base_url} and "
                f"select '{model}'. Works offline once the model is pulled."
            ),
        }


copilot_tester = CopilotTester()
