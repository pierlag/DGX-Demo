"""Scrape vLLM's own Prometheus endpoint and fold it into the dashboard.

The live dashboard's ``MetricsStore`` only sees inference that is routed
*through* this backend (the test chat + the MCP subprocess). Traffic that hits
the vLLM server directly — most importantly the **offline GitHub Copilot CLI**
and any external OpenAI-compatible client — bypasses the backend entirely and so
never shows up as throughput / latency / requests / tokens.

vLLM already exposes an authoritative Prometheus endpoint at
``http://{vllm_host}:{vllm_port}/metrics`` covering *every* request it serves.
This module polls that endpoint, parses the ``vllm:*`` families, derives a small
engine summary (tokens in/out, requests, live throughput, latency p50/p95/avg)
and stores it on the shared ``metrics_store`` so the dashboard reflects ALL vLLM
activity regardless of how the request reached the engine.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from app.config import settings
from app.services.metrics import metrics_store


# --------------------------------------------------------------------- parsing
def _parse_labels(labelstr: str) -> dict[str, str]:
    """Parse a Prometheus label block (without the surrounding braces)."""
    labels: dict[str, str] = {}
    i = 0
    n = len(labelstr)
    while i < n:
        eq = labelstr.find("=", i)
        if eq == -1:
            break
        key = labelstr[i:eq].strip()
        # value is a double-quoted string starting right after '='
        q1 = labelstr.find('"', eq)
        if q1 == -1:
            break
        # find the closing quote, honouring backslash escapes
        j = q1 + 1
        buf: list[str] = []
        while j < n:
            c = labelstr[j]
            if c == "\\" and j + 1 < n:
                buf.append(labelstr[j + 1])
                j += 2
                continue
            if c == '"':
                break
            buf.append(c)
            j += 1
        labels[key] = "".join(buf)
        # advance past the closing quote and an optional comma
        i = j + 1
        while i < n and labelstr[i] in ", ":
            i += 1
    return labels


def parse_prometheus(text: str) -> dict[str, list[tuple[dict[str, str], float]]]:
    """Parse Prometheus exposition text into ``name -> [(labels, value), ...]``."""
    families: dict[str, list[tuple[dict[str, str], float]]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            metric_part, value_str = line.rsplit(" ", 1)
        except ValueError:
            continue
        try:
            value = float(value_str)
        except ValueError:
            # skip NaN / +Inf gauges we don't use
            continue
        metric_part = metric_part.strip()
        if metric_part.endswith("}") and "{" in metric_part:
            name, labelstr = metric_part.split("{", 1)
            labels = _parse_labels(labelstr[:-1])
        else:
            name, labels = metric_part, {}
        families.setdefault(name.strip(), []).append((labels, value))
    return families


def _sum(families: dict, name: str) -> float:
    return sum(v for _, v in families.get(name, []))


def _hist_quantiles(buckets: list[tuple[dict[str, str], float]],
                    quantiles: list[float]) -> dict[float, float]:
    """Estimate quantiles (in the histogram's native unit) from ``*_bucket``.

    All vLLM series share the same bucket boundaries, so summing the cumulative
    counts across label sets at each ``le`` yields a single aggregate histogram.
    """
    agg: dict[float, float] = {}
    for labels, value in buckets:
        le = labels.get("le")
        if le is None:
            continue
        le_f = float("inf") if le in ("+Inf", "Inf") else _safe_float(le)
        if le_f is None:
            continue
        agg[le_f] = agg.get(le_f, 0.0) + value
    if not agg:
        return {q: 0.0 for q in quantiles}
    les = sorted(agg)
    total = agg[les[-1]]  # cumulative count at the +Inf bucket
    res: dict[float, float] = {}
    for q in quantiles:
        if total <= 0:
            res[q] = 0.0
            continue
        target = q * total
        chosen = les[-1]
        for le in les:
            if agg[le] >= target:
                chosen = le
                break
        res[q] = 0.0 if chosen == float("inf") else chosen
    return res


def _safe_float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


# ------------------------------------------------------------------- sampler
class VllmMetricsSampler:
    """Periodically scrape vLLM ``/metrics`` and push a summary to the store."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._prev_gen: float | None = None
        self._prev_ts: float | None = None

    @property
    def _url(self) -> str:
        return f"http://{settings.vllm_host}:{settings.vllm_port}/metrics"

    def _summarize(self, families: dict) -> dict:
        now = time.time()
        tokens_in = _sum(families, "vllm:prompt_tokens_total")
        tokens_out = _sum(families, "vllm:generation_tokens_total")
        requests = _sum(families, "vllm:request_success_total")
        running = _sum(families, "vllm:num_requests_running")
        waiting = _sum(families, "vllm:num_requests_waiting")

        lat_sum = _sum(families, "vllm:e2e_request_latency_seconds_sum")
        lat_count = _sum(families, "vllm:e2e_request_latency_seconds_count")
        avg_ms = (lat_sum / lat_count * 1000.0) if lat_count > 0 else 0.0
        pct = _hist_quantiles(
            families.get("vllm:e2e_request_latency_seconds_bucket", []),
            [0.5, 0.95],
        )

        ttft_sum = _sum(families, "vllm:time_to_first_token_seconds_sum")
        ttft_count = _sum(families, "vllm:time_to_first_token_seconds_count")
        ttft_ms = (ttft_sum / ttft_count * 1000.0) if ttft_count > 0 else 0.0

        # Live generation throughput from the delta between consecutive scrapes.
        tps = 0.0
        if self._prev_gen is not None and self._prev_ts is not None:
            dt = now - self._prev_ts
            delta = tokens_out - self._prev_gen
            if dt > 0 and delta >= 0:
                tps = delta / dt
        self._prev_gen = tokens_out
        self._prev_ts = now

        model = ""
        for labels, _ in families.get("vllm:generation_tokens_total", []):
            model = labels.get("model_name", "") or model
            if model:
                break

        return {
            "up": True,
            "model": model,
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "requests": int(requests),
            "running": int(running),
            "waiting": int(waiting),
            "tokens_per_second": round(tps, 1),
            "latency": {
                "p50": round(pct.get(0.5, 0.0) * 1000.0, 1),
                "p95": round(pct.get(0.95, 0.0) * 1000.0, 1),
                "avg": round(avg_ms, 1),
            },
            "ttft_ms": round(ttft_ms, 1),
        }

    async def _loop(self) -> None:
        async with httpx.AsyncClient(timeout=4.0) as client:
            while True:
                try:
                    r = await client.get(self._url)
                    r.raise_for_status()
                    families = parse_prometheus(r.text)
                    metrics_store.set_vllm(self._summarize(families))
                except Exception:
                    # vLLM down / not launched yet: report offline and reset the
                    # throughput baseline so it doesn't spike on the next success.
                    self._prev_gen = None
                    self._prev_ts = None
                    metrics_store.set_vllm({"up": False})
                await asyncio.sleep(settings.metrics_sample_interval_s)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


vllm_metrics_sampler = VllmMetricsSampler()
