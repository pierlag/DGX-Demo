"""Local test chat for the MCP / RAG server.

Streams a grounded answer: retrieves local context from Qdrant, then calls the
local vLLM OpenAI-compatible server with the configured meta prompt. Records
latency and token usage into the metrics store (powering the dashboard).
"""
from __future__ import annotations

import json
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.services.metrics import metrics_store
from app.services.mcp_manager import mcp_manager
from app.services.rag_pipeline import rag_pipeline
from app.services.vllm_manager import vllm_manager

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    use_rag: bool = True
    top_k: int = 4
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None


@router.post("")
async def chat(req: ChatRequest):
    start = time.time()
    sources = []
    context = ""
    if req.use_rag:
        hits = rag_pipeline.query(req.message, top_k=req.top_k)
        sources = [{"source": h["source"], "score": h["score"]} for h in hits]
        context = "\n\n".join(
            f"[{h['source']}] {h['text']}" for h in hits if h.get("text")
        )

    meta = mcp_manager.get_config().get("meta_prompt", settings.mcp_meta_prompt)
    user_prompt = (
        f"Context:\n{context}\n\nQuestion: {req.message}"
        if context else req.message
    )
    model = vllm_manager.state.model or "local-model"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": meta},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if req.tools:
        payload["tools"] = req.tools
    if req.tool_choice is not None:
        payload["tool_choice"] = req.tool_choice

    async def gen():
        # Emit sources first
        yield json.dumps({"type": "sources", "sources": sources}) + "\n"
        tokens_out = 0
        tokens_in = 0
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST", f"{settings.vllm_base_url}/chat/completions",
                    json=payload,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except Exception:
                            continue
                        choices = obj.get("choices") or []
                        if choices:
                            delta_obj = choices[0].get("delta", {})
                            delta = delta_obj.get("content")
                            if delta:
                                tokens_out += 1
                                yield json.dumps({"type": "token", "text": delta}) + "\n"
                            tool_calls = delta_obj.get("tool_calls")
                            if tool_calls:
                                yield json.dumps({
                                    "type": "tool_calls",
                                    "tool_calls": tool_calls,
                                }) + "\n"
                        if obj.get("usage"):
                            tokens_in = obj["usage"].get("prompt_tokens", tokens_in)
                            tokens_out = obj["usage"].get("completion_tokens", tokens_out)
        except Exception as exc:
            yield json.dumps({
                "type": "error",
                "text": f"vLLM indisponible: {exc}. "
                        f"Contexte récupéré depuis {len(sources)} sources.",
            }) + "\n"

        latency_ms = (time.time() - start) * 1000
        metrics_store.record_request(latency_ms, tokens_in, tokens_out, "chat")
        yield json.dumps({
            "type": "done",
            "latency_ms": round(latency_ms, 1),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
