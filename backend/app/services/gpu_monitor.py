"""GPU monitoring sampler.

Uses NVML (nvidia-ml-py) to sample GPU utilization, memory, power and
temperature. The GB10 (DGX Spark) uses *unified* memory, so device memory
queries may be unsupported; we fall back to system memory via psutil so the
dashboard always shows meaningful numbers.
"""
from __future__ import annotations

import asyncio
import time

import psutil

from app.config import settings
from app.services.metrics import GpuSample, metrics_store

try:
    import pynvml  # provided by nvidia-ml-py
    _NVML_AVAILABLE = True
except Exception:  # pragma: no cover
    pynvml = None
    _NVML_AVAILABLE = False


class GpuMonitor:
    def __init__(self) -> None:
        self._handle = None
        self._nvml_ok = False
        self._task: asyncio.Task | None = None

    def init(self) -> None:
        if not _NVML_AVAILABLE:
            return
        try:
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml_ok = True
        except Exception:
            self._nvml_ok = False

    def _sample(self) -> GpuSample:
        ts = time.time()
        gpu_util = 0.0
        mem_used_mb = 0.0
        mem_total_mb = 0.0
        power_w = 0.0
        temp_c = 0.0

        if self._nvml_ok and self._handle is not None:
            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
                gpu_util = float(util.gpu)
            except Exception:
                pass
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
                mem_used_mb = mem.used / (1024 ** 2)
                mem_total_mb = mem.total / (1024 ** 2)
            except Exception:
                # GB10 unified memory: device memory not exposed -> use system RAM
                pass
            try:
                power_w = pynvml.nvmlDeviceGetPowerUsage(self._handle) / 1000.0
            except Exception:
                pass
            try:
                temp_c = float(
                    pynvml.nvmlDeviceGetTemperature(
                        self._handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                )
            except Exception:
                pass

        # Fallback / unified-memory: report system memory
        if mem_total_mb <= 0:
            vm = psutil.virtual_memory()
            mem_total_mb = vm.total / (1024 ** 2)
            mem_used_mb = vm.used / (1024 ** 2)

        return GpuSample(
            ts=ts,
            gpu_util=gpu_util,
            mem_used_mb=mem_used_mb,
            mem_total_mb=mem_total_mb,
            power_w=power_w,
            temp_c=temp_c,
        )

    async def _loop(self) -> None:
        while True:
            try:
                metrics_store.add_gpu_sample(self._sample())
            except Exception:
                pass
            await asyncio.sleep(settings.metrics_sample_interval_s)

    def start(self) -> None:
        self.init()
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._nvml_ok:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


gpu_monitor = GpuMonitor()
