"""Prometheus text exposition for the DGX Demo backend.

Renders the live ``metrics_store`` snapshot as Prometheus metrics so the bundled
Grafana stack (Prometheus + Loki + Promtail + Grafana, see the repo root
``observability/`` folder + ``docker-compose.yml``) can scrape and visualise it.

Zero extra dependency: the exposition format is plain text, so we build it by
hand instead of pulling in ``prometheus_client``. Prometheus scrapes this at
``GET /metrics`` on the backend (default ``host.docker.internal:8000``).

Exposed families:
  * GPU / NVML       — utilisation, unified memory, power, temperature
  * vLLM throughput  — tokens/s, token + request counters, latency p50/p95/avg
  * RAG / Qdrant     — indexed files + chunks
  * Copilot CLI      — turns, tool calls, errors, session state, last latency
  * Energy & carbon  — cumulative Wh + gCO2 (France grid)
"""
from __future__ import annotations

from app.services.metrics import metrics_store


def _line(name: str, value: float | int, labels: str = "") -> str:
    return f"{name}{labels} {value}"


def render() -> str:
    """Return the full Prometheus exposition text for the current snapshot."""
    snap = metrics_store.snapshot()
    cur = snap["current"]
    lat = snap["latency"]
    counters = snap["counters"]
    cop = snap["copilot"]
    vllm = snap.get("vllm", {})

    out: list[str] = []

    def metric(name: str, help_text: str, mtype: str,
               value: float | int, labels: str = "") -> None:
        out.append(f"# HELP {name} {help_text}")
        out.append(f"# TYPE {name} {mtype}")
        out.append(_line(name, value, labels))

    # --- GPU / NVML (unified memory on GB10) ---
    metric("dgx_gpu_utilization_percent",
           "GPU utilisation (percent).", "gauge", cur["gpu_util"])
    metric("dgx_gpu_memory_used_mb",
           "Used (unified) memory in MB.", "gauge", cur["mem_used_mb"])
    metric("dgx_gpu_memory_total_mb",
           "Total (unified) memory in MB.", "gauge", cur["mem_total_mb"])
    metric("dgx_gpu_power_watts",
           "GPU power draw in watts.", "gauge", cur["power_w"])
    metric("dgx_gpu_temperature_celsius",
           "GPU temperature in celsius.", "gauge", cur["temp_c"])

    # --- vLLM throughput ---
    metric("dgx_tokens_per_second",
           "Output tokens per second (10s rolling window).", "gauge",
           snap["tokens_per_second"])
    metric("dgx_tokens_in_total",
           "Total input tokens processed.", "counter",
           counters["total_tokens_in"])
    metric("dgx_tokens_out_total",
           "Total output tokens generated.", "counter",
           counters["total_tokens_out"])
    metric("dgx_requests_total",
           "Total inference requests handled.", "counter",
           counters["total_requests"])
    metric("dgx_connected_clients",
           "Currently connected MCP clients.", "gauge",
           counters["connected_clients"])

    out.append("# HELP dgx_request_latency_ms Request latency (ms).")
    out.append("# TYPE dgx_request_latency_ms gauge")
    out.append(_line("dgx_request_latency_ms", lat["p50"], '{quantile="0.5"}'))
    out.append(_line("dgx_request_latency_ms", lat["p95"], '{quantile="0.95"}'))
    out.append(_line("dgx_request_latency_ms", lat["avg"], '{quantile="avg"}'))

    # --- vLLM engine (scraped from vLLM's own /metrics, covers ALL traffic
    # incl. the offline Copilot CLI / external OpenAI-compatible clients) ---
    if vllm.get("up"):
        vlat = vllm.get("latency", {})
        metric("dgx_vllm_up",
               "1 when the vLLM engine /metrics endpoint is reachable.",
               "gauge", 1)
        metric("dgx_vllm_tokens_per_second",
               "vLLM live generation throughput (tokens/s).", "gauge",
               vllm.get("tokens_per_second", 0.0))
        metric("dgx_vllm_prompt_tokens_total",
               "vLLM cumulative prompt (input) tokens.", "counter",
               vllm.get("tokens_in", 0))
        metric("dgx_vllm_generation_tokens_total",
               "vLLM cumulative generation (output) tokens.", "counter",
               vllm.get("tokens_out", 0))
        metric("dgx_vllm_requests_total",
               "vLLM cumulative successful requests.", "counter",
               vllm.get("requests", 0))
        metric("dgx_vllm_requests_running",
               "vLLM requests currently running.", "gauge",
               vllm.get("running", 0))
        metric("dgx_vllm_requests_waiting",
               "vLLM requests currently queued.", "gauge",
               vllm.get("waiting", 0))
        out.append("# HELP dgx_vllm_latency_ms vLLM end-to-end request latency (ms).")
        out.append("# TYPE dgx_vllm_latency_ms gauge")
        out.append(_line("dgx_vllm_latency_ms", vlat.get("p50", 0.0), '{quantile="0.5"}'))
        out.append(_line("dgx_vllm_latency_ms", vlat.get("p95", 0.0), '{quantile="0.95"}'))
        out.append(_line("dgx_vllm_latency_ms", vlat.get("avg", 0.0), '{quantile="avg"}'))
    else:
        metric("dgx_vllm_up",
               "1 when the vLLM engine /metrics endpoint is reachable.",
               "gauge", 0)

    # --- RAG / Qdrant ---
    metric("dgx_rag_indexed_files",
           "Documents indexed in the Qdrant collection.", "gauge",
           counters["indexed_files"])
    metric("dgx_rag_indexed_chunks",
           "Vector chunks indexed in the Qdrant collection.", "gauge",
           counters["indexed_chunks"])

    # --- Copilot CLI activity (offline BYOK against vLLM) ---
    metric("dgx_copilot_turns_total",
           "Copilot BYOK validation turns executed.", "counter", cop["turns"])
    metric("dgx_copilot_tool_calls_total",
           "Copilot turns that returned structured tool_calls.", "counter",
           cop["tool_calls"])
    metric("dgx_copilot_errors_total",
           "Copilot validation turns that failed.", "counter", cop["errors"])
    metric("dgx_copilot_session_active",
           "1 when an offline Copilot session is wired to vLLM.", "gauge",
           1 if cop["session_active"] else 0)
    metric("dgx_copilot_last_latency_ms",
           "Latency of the last Copilot validation turn (ms).", "gauge",
           cop["last_latency_ms"])

    # --- Energy & carbon (France grid) ---
    metric("dgx_energy_wh_total",
           "Cumulative estimated energy across all workloads (Wh).", "counter",
           counters["total_energy_wh"])
    metric("dgx_co2_grams_total",
           "Cumulative estimated CO2 emissions (grams, France grid).", "counter",
           counters["total_co2_g"])
    metric("dgx_carbon_intensity_g_per_kwh",
           "Carbon intensity of the electricity mix (gCO2eq/kWh).", "gauge",
           snap["carbon_intensity_g_per_kwh"])

    return "\n".join(out) + "\n"
