"""MCP server exposing RAG tools over streamable HTTP.

Run standalone:  python -m app.services.mcp_server

It exposes two tools backed by the local Qdrant RAG base and the local vLLM
OpenAI-compatible server:
  * rag_search(query)  -> top matching chunks with sources
  * rag_answer(question) -> grounded answer using the configured meta prompt

The streamable-HTTP transport is reachable by external MCP clients via the
devtunnel public URL.
"""
from __future__ import annotations

import time

import httpx
from mcp.server.fastmcp import Context, FastMCP

from app.config import settings
from app.services.rag_pipeline import rag_pipeline
from app.services.state_store import load_state

mcp = FastMCP("vibeMCP-RAG", host=settings.mcp_host, port=settings.mcp_port)

# The MCP server runs in its own process, so it cannot share the backend's
# in-memory metrics store. Instead it forwards activity to the backend over
# HTTP so the live dashboard stays consistent.
_BACKEND_INGEST_URL = f"http://127.0.0.1:{settings.port}/api/metrics/ingest"


def _client_id(ctx: Context | None) -> str:
    """Derive a stable-ish client identifier from the MCP request context."""
    if ctx is None:
        return "mcp-anonymous"
    for attr in ("client_id", "request_id"):
        val = getattr(ctx, attr, None)
        if val:
            return str(val)
    # Fall back to the session object identity (stable per connection).
    session = getattr(ctx, "session", None)
    if session is not None:
        return f"session-{id(session)}"
    return "mcp-anonymous"


def _report_metrics(
    *,
    client_id: str,
    latency_ms: float = 0.0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    endpoint: str = "mcp",
    record_request: bool = True,
) -> None:
    """Best-effort push of metrics to the backend (never raises)."""
    try:
        with httpx.Client(timeout=2.0) as client:
            client.post(
                _BACKEND_INGEST_URL,
                json={
                    "client_id": client_id,
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "endpoint": endpoint,
                    "record_request": record_request,
                },
            )
    except Exception:
        pass


def _meta_prompt() -> str:
    cfg = load_state("mcp_config", {"meta_prompt": settings.mcp_meta_prompt})
    return cfg.get("meta_prompt", settings.mcp_meta_prompt)


def _model_name() -> str:
    cfg = load_state("vllm_state", {})
    return cfg.get("model", "local-model")


@mcp.tool()
def rag_search(query: str, top_k: int = 4, ctx: Context = None) -> list[dict]:
    """Search the local document base and return the most relevant chunks."""
    start = time.time()
    cid = _client_id(ctx)
    results = rag_pipeline.query(query, top_k=top_k)
    _report_metrics(
        client_id=cid,
        latency_ms=(time.time() - start) * 1000,
        endpoint="mcp/rag_search",
    )
    return results


@mcp.tool()
def rag_answer(question: str, top_k: int = 4, ctx: Context = None) -> str:
    """Answer a question using retrieved local context + the local vLLM model."""
    start = time.time()
    cid = _client_id(ctx)
    hits = rag_pipeline.query(question, top_k=top_k)
    context = "\n\n".join(
        f"[{h['source']}] {h['text']}" for h in hits if h.get("text")
    )
    sys_prompt = _meta_prompt()
    user_prompt = (
        f"Context:\n{context}\n\nQuestion: {question}\n\n"
        "Answer using only the context above and cite the source files."
    )
    payload = {
        "model": _model_name(),
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 512,
    }
    try:
        with httpx.Client(timeout=120) as client:
            r = client.post(f"{settings.vllm_base_url}/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        _report_metrics(
            client_id=cid,
            latency_ms=(time.time() - start) * 1000,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            endpoint="mcp/rag_answer",
        )
        return answer
    except Exception as exc:
        # Still report the client/request so the dashboard reflects activity.
        _report_metrics(
            client_id=cid,
            latency_ms=(time.time() - start) * 1000,
            endpoint="mcp/rag_answer",
        )
        return f"[vLLM indisponible] {exc}\n\nContexte trouvé:\n{context}"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
