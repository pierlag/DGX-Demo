"""In-memory metrics store shared across the app.

Holds rolling history (default 15 min) of GPU / memory samples plus running
counters for tokens processed, requests handled, latencies and connected MCP
clients. This is the single source of truth for the live dashboard.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from app.config import settings


@dataclass
class GpuSample:
    ts: float
    gpu_util: float          # percent 0-100
    mem_used_mb: float       # MB (unified memory on GB10)
    mem_total_mb: float      # MB
    power_w: float           # watts
    temp_c: float            # celsius


@dataclass
class RequestRecord:
    ts: float
    latency_ms: float
    tokens_in: int
    tokens_out: int
    endpoint: str


class MetricsStore:
    """Thread-safe metrics store (sampler thread + request handlers write)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        history_seconds = settings.metrics_history_minutes * 60
        maxlen = int(history_seconds / max(settings.metrics_sample_interval_s, 0.5)) + 10
        self.gpu_history: Deque[GpuSample] = deque(maxlen=maxlen)
        self.request_history: Deque[RequestRecord] = deque(maxlen=2000)

        # Running counters
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.total_requests: int = 0
        self.connected_clients: int = 0
        self.indexed_files: int = 0
        self.indexed_chunks: int = 0

        # tokens/sec rolling (last 10s window of out tokens)
        self._token_window: Deque[tuple[float, int]] = deque(maxlen=500)

        # MCP client tracking: client_id -> last_seen timestamp.
        # A client is "connected" if seen within client_ttl_s seconds.
        self._clients: dict[str, float] = {}
        self.client_ttl_s: float = 120.0

    # --- writers ---
    def add_gpu_sample(self, sample: GpuSample) -> None:
        with self._lock:
            self.gpu_history.append(sample)

    def record_request(self, latency_ms: float, tokens_in: int,
                       tokens_out: int, endpoint: str) -> None:
        now = time.time()
        with self._lock:
            self.total_requests += 1
            self.total_tokens_in += tokens_in
            self.total_tokens_out += tokens_out
            self.request_history.append(
                RequestRecord(now, latency_ms, tokens_in, tokens_out, endpoint)
            )
            self._token_window.append((now, tokens_out))

    def set_clients(self, n: int) -> None:
        with self._lock:
            self.connected_clients = max(0, n)

    def touch_client(self, client_id: str) -> None:
        """Mark an MCP client as active and recompute the live client count."""
        now = time.time()
        with self._lock:
            self._clients[client_id] = now
            # Prune stale clients and recompute connected count.
            cutoff = now - self.client_ttl_s
            self._clients = {
                cid: ts for cid, ts in self._clients.items() if ts >= cutoff
            }
            self.connected_clients = len(self._clients)

    def _prune_clients_locked(self) -> None:
        """Drop clients not seen within the TTL (caller must hold the lock)."""
        cutoff = time.time() - self.client_ttl_s
        self._clients = {
            cid: ts for cid, ts in self._clients.items() if ts >= cutoff
        }
        self.connected_clients = len(self._clients)

    def set_index_stats(self, files: int, chunks: int) -> None:
        with self._lock:
            self.indexed_files = files
            self.indexed_chunks = chunks

    # --- readers ---
    def tokens_per_second(self, window_s: float = 10.0) -> float:
        now = time.time()
        with self._lock:
            recent = [(t, n) for t, n in self._token_window if now - t <= window_s]
        if not recent:
            return 0.0
        total = sum(n for _, n in recent)
        span = max(now - recent[0][0], 1e-6)
        return total / span

    def latency_percentiles(self) -> dict[str, float]:
        with self._lock:
            lats = sorted(r.latency_ms for r in self.request_history)
        if not lats:
            return {"p50": 0.0, "p95": 0.0, "avg": 0.0}

        def pct(p: float) -> float:
            idx = min(len(lats) - 1, int(p * len(lats)))
            return lats[idx]

        return {
            "p50": pct(0.50),
            "p95": pct(0.95),
            "avg": sum(lats) / len(lats),
        }

    def snapshot(self) -> dict:
        with self._lock:
            self._prune_clients_locked()
            latest = self.gpu_history[-1] if self.gpu_history else None
            history = [
                {
                    "ts": s.ts,
                    "gpu_util": round(s.gpu_util, 1),
                    "mem_used_mb": round(s.mem_used_mb, 1),
                    "mem_total_mb": round(s.mem_total_mb, 1),
                    "power_w": round(s.power_w, 1),
                    "temp_c": round(s.temp_c, 1),
                }
                for s in self.gpu_history
            ]
            counters = {
                "total_tokens_in": self.total_tokens_in,
                "total_tokens_out": self.total_tokens_out,
                "total_requests": self.total_requests,
                "connected_clients": self.connected_clients,
                "indexed_files": self.indexed_files,
                "indexed_chunks": self.indexed_chunks,
            }
        return {
            "current": {
                "gpu_util": round(latest.gpu_util, 1) if latest else 0.0,
                "mem_used_mb": round(latest.mem_used_mb, 1) if latest else 0.0,
                "mem_total_mb": round(latest.mem_total_mb, 1) if latest else 0.0,
                "power_w": round(latest.power_w, 1) if latest else 0.0,
                "temp_c": round(latest.temp_c, 1) if latest else 0.0,
            },
            "tokens_per_second": round(self.tokens_per_second(), 1),
            "latency": {k: round(v, 1) for k, v in self.latency_percentiles().items()},
            "counters": counters,
            "history": history,
        }


metrics_store = MetricsStore()
