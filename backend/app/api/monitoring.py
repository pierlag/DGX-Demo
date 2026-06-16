"""Monitoring: live metrics over WebSocket + snapshot endpoint."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.services.metrics import metrics_store

router = APIRouter(tags=["monitoring"])


class MetricsIngest(BaseModel):
    """Payload pushed by out-of-process workers (e.g. the MCP subprocess)."""
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    endpoint: str = "mcp"
    client_id: str | None = None
    record_request: bool = True


@router.get("/api/metrics/snapshot")
def snapshot():
    return metrics_store.snapshot()


@router.post("/api/metrics/ingest")
def ingest(payload: MetricsIngest):
    """Receive metrics from the MCP subprocess and merge into the shared store.

    The MCP server runs in its own process with a separate in-memory store, so
    it forwards request/token/client activity here to keep the dashboard
    consistent.
    """
    if payload.client_id:
        metrics_store.touch_client(payload.client_id)
    if payload.record_request:
        metrics_store.record_request(
            latency_ms=payload.latency_ms,
            tokens_in=payload.tokens_in,
            tokens_out=payload.tokens_out,
            endpoint=payload.endpoint,
        )
    return {"ok": True}


@router.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(metrics_store.snapshot())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        return
