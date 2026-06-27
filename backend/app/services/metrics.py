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
    power_w: float = 0.0       # GPU power draw at request time (watts)
    energy_wh: float = 0.0     # estimated energy consumed by the request (Wh)
    co2_g: float = 0.0         # estimated CO2 emissions (grams, France grid)


@dataclass
class StudioRecord:
    ts: float
    kind: str                  # "image" (text->image) | "mesh" (image->3D)
    duration_s: float          # wall-clock generation time (seconds)
    label: str = ""            # prompt or source asset name
    model: str = ""            # model id used for the generation
    power_w: float = 0.0       # GPU power draw at generation time (watts)
    energy_wh: float = 0.0     # estimated energy consumed (Wh)
    co2_g: float = 0.0         # estimated CO2 emissions (grams, France grid)


@dataclass
class CopilotRecord:
    ts: float
    test: str                  # validation test name (models/chat/stream/tools)
    ok: bool                   # pass/fail
    latency_ms: float          # round-trip latency of the test turn
    detail: str = ""           # short human-readable result / error


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

        # Studio 3D (text->image + image->3D) counters and rolling history.
        self.studio_requests: int = 0
        self.studio_history: Deque[StudioRecord] = deque(maxlen=500)

        # GitHub Copilot CLI (offline BYOK against the local vLLM server).
        self.copilot_turns: int = 0
        self.copilot_tool_calls: int = 0
        self.copilot_errors: int = 0
        self.copilot_session_active: bool = False
        self.copilot_last_latency_ms: float = 0.0
        self.copilot_history: Deque[CopilotRecord] = deque(maxlen=500)

        # Monotonic energy/CO2 totals (Wh / grams) across every workload, so the
        # Prometheus exporter can publish true cumulative counters.
        self.total_energy_wh: float = 0.0
        self.total_co2_g: float = 0.0

        # Latest summary scraped from vLLM's own Prometheus endpoint. Captures
        # ALL engine traffic (including the offline Copilot CLI / external
        # clients) that bypasses this backend. Updated by the vLLM sampler.
        self._vllm: dict = {"up": False}

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
            # Estimate energy/CO2 from the live GPU power draw (fallback to the
            # configured average power when no sample is available yet).
            power_w = (
                self.gpu_history[-1].power_w
                if self.gpu_history
                else settings.inference_power_w
            )
            energy_wh = power_w * (latency_ms / 1000.0) / 3600.0
            co2_g = (energy_wh / 1000.0) * settings.carbon_intensity_g_per_kwh
            self.total_energy_wh += energy_wh
            self.total_co2_g += co2_g
            self.request_history.append(
                RequestRecord(now, latency_ms, tokens_in, tokens_out, endpoint,
                              power_w, energy_wh, co2_g)
            )
            self._token_window.append((now, tokens_out))

    def record_studio(self, kind: str, duration_s: float,
                      label: str = "", model: str = "") -> None:
        """Record a Studio 3D generation and estimate its energy/CO2 cost."""
        now = time.time()
        with self._lock:
            self.studio_requests += 1
            power_w = (
                self.gpu_history[-1].power_w
                if self.gpu_history
                else settings.inference_power_w
            )
            energy_wh = power_w * (duration_s / 3600.0)
            co2_g = (energy_wh / 1000.0) * settings.carbon_intensity_g_per_kwh
            self.total_energy_wh += energy_wh
            self.total_co2_g += co2_g
            self.studio_history.append(
                StudioRecord(now, kind, duration_s, label, model,
                             power_w, energy_wh, co2_g)
            )

    def record_copilot(self, test: str, ok: bool, latency_ms: float,
                       detail: str = "", tool_calls: int = 0) -> None:
        """Record one Copilot BYOK validation turn (run against the vLLM server).

        Feeds the dashboard + Grafana "Copilot CLI activity" panels: every test
        counts as a turn, tool-call tests bump the tool-call counter, failures
        bump the error counter, and the local inference cost is added to the
        global energy/CO2 totals.
        """
        now = time.time()
        with self._lock:
            self.copilot_turns += 1
            self.copilot_tool_calls += max(0, tool_calls)
            if not ok:
                self.copilot_errors += 1
            self.copilot_last_latency_ms = latency_ms
            self.copilot_history.append(
                CopilotRecord(now, test, ok, latency_ms, detail)
            )
            power_w = (
                self.gpu_history[-1].power_w
                if self.gpu_history
                else settings.inference_power_w
            )
            energy_wh = power_w * (latency_ms / 1000.0) / 3600.0
            self.total_energy_wh += energy_wh
            self.total_co2_g += (
                energy_wh / 1000.0
            ) * settings.carbon_intensity_g_per_kwh

    def set_copilot_session(self, active: bool) -> None:
        with self._lock:
            self.copilot_session_active = bool(active)

    def set_vllm(self, data: dict) -> None:
        """Store the latest summary scraped from vLLM's Prometheus endpoint."""
        with self._lock:
            self._vllm = dict(data)

    def recent_copilot(self, n: int = 8) -> list[dict]:
        """Return the ``n`` most recent Copilot validation turns, newest first."""
        with self._lock:
            items = list(self.copilot_history)[-n:]
        return [
            {
                "ts": r.ts,
                "test": r.test,
                "ok": r.ok,
                "latency_ms": round(r.latency_ms, 1),
                "detail": r.detail,
            }
            for r in reversed(items)
        ]

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

    def recent_requests(self, n: int = 3) -> list[dict]:
        """Return the ``n`` most recent requests, newest first."""
        with self._lock:
            items = list(self.request_history)[-n:]
        return [
            {
                "ts": r.ts,
                "latency_ms": round(r.latency_ms, 1),
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "power_w": round(r.power_w, 1),
                "energy_wh": round(r.energy_wh, 4),
                "co2_g": round(r.co2_g, 4),
                "endpoint": r.endpoint,
            }
            for r in reversed(items)
        ]

    def recent_studio(self, n: int = 5) -> list[dict]:
        """Return the ``n`` most recent Studio 3D generations, newest first."""
        with self._lock:
            items = list(self.studio_history)[-n:]
        return [
            {
                "ts": r.ts,
                "kind": r.kind,
                "duration_s": round(r.duration_s, 1),
                "label": r.label,
                "model": r.model,
                "power_w": round(r.power_w, 1),
                "energy_wh": round(r.energy_wh, 4),
                "co2_g": round(r.co2_g, 4),
            }
            for r in reversed(items)
        ]

    def studio_totals(self) -> dict[str, float]:
        """Aggregate energy/CO2 across all recorded Studio 3D generations."""
        with self._lock:
            records = list(self.studio_history)
            requests = self.studio_requests
        return {
            "requests": requests,
            "images": sum(1 for r in records if r.kind == "image"),
            "meshes": sum(1 for r in records if r.kind == "mesh"),
            "energy_wh": round(sum(r.energy_wh for r in records), 4),
            "co2_g": round(sum(r.co2_g for r in records), 4),
        }

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
                "total_energy_wh": round(self.total_energy_wh, 4),
                "total_co2_g": round(self.total_co2_g, 4),
            }
            copilot = {
                "turns": self.copilot_turns,
                "tool_calls": self.copilot_tool_calls,
                "errors": self.copilot_errors,
                "session_active": self.copilot_session_active,
                "last_latency_ms": round(self.copilot_last_latency_ms, 1),
            }
            vllm = dict(self._vllm)
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
            "recent_requests": self.recent_requests(3),
            "studio": {
                "totals": self.studio_totals(),
                "recent": self.recent_studio(5),
            },
            "copilot": {
                **copilot,
                "recent": self.recent_copilot(8),
            },
            "vllm": vllm,
            "carbon_intensity_g_per_kwh": settings.carbon_intensity_g_per_kwh,
            "history": history,
        }


metrics_store = MetricsStore()
