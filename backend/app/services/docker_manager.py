"""Docker container management and monitoring.

Lists running/stopped containers, retrieves stats (CPU, memory, GPU),
allows start/stop operations, and reads container configurations.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class ContainerStats:
    """Real-time stats for a container."""
    cpu_percent: float  # % of host CPU
    memory_usage_mb: float  # Actual usage in MB
    memory_limit_mb: float  # Limit in MB (0 if unlimited)
    memory_percent: float  # % of limit (or total if unlimited)
    net_in_bytes: float  # Network bytes in
    net_out_bytes: float  # Network bytes out
    block_in_bytes: float  # Block I/O bytes in
    block_out_bytes: float  # Block I/O bytes out


@dataclass
class Container:
    """A Docker container with metadata and stats."""
    id: str  # Short ID
    name: str
    image: str
    status: str  # "running", "exited", etc.
    created: str  # ISO timestamp
    ports: dict[str, list[dict[str, str]]]  # Port mappings
    labels: dict[str, str]  # Container labels
    stats: ContainerStats | None = None  # Live stats (only if running)


class DockerManager:
    def __init__(self) -> None:
        self._docker = None

    def _docker_bin(self) -> str | None:
        """Get Docker binary path."""
        if self._docker is None:
            self._docker = shutil.which("docker")
        return self._docker

    def list_containers(self, all_: bool = True) -> list[Container]:
        """List Docker containers with metadata."""
        docker = self._docker_bin()
        if not docker:
            return []

        try:
            # Get all containers with full format (NDJSON output)
            cmd = [docker, "ps", "-a" if all_ else "", "--format", "json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                return []
            
            containers = []
            # Docker ps --format json outputs one JSON object per line (NDJSON)
            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    containers.append(Container(
                        id=data.get("ID", "")[:12],
                        name=data.get("Names", ""),
                        image=data.get("Image", ""),
                        status=data.get("Status", ""),
                        created=data.get("CreatedAt", ""),
                        ports=self._parse_ports(data.get("Ports", "")),
                        labels=self._parse_labels(data.get("Labels", "")),
                    ))
                except json.JSONDecodeError:
                    continue
            return containers
        except Exception:
            return []

    def _parse_ports(self, ports_str: str) -> dict:
        """Parse Docker ports string to dict."""
        # Example: "0.0.0.0:6333->6333/tcp, [::]:6333->6333/tcp"
        if not ports_str:
            return {}
        # For now, return raw string in a dict
        return {"raw": ports_str}

    def _parse_labels(self, labels_str: str) -> dict:
        """Parse Docker labels string to dict."""
        if not labels_str:
            return {}
        # Labels come as comma-separated key=value pairs
        labels = {}
        try:
            for pair in labels_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    labels[k.strip()] = v.strip()
        except Exception:
            pass
        return labels

    def get_container_stats(self, container_id: str) -> ContainerStats | None:
        """Get real-time stats for a running container."""
        docker = self._docker_bin()
        if not docker:
            return None

        try:
            # Get stats stream (single sample via no-stream=false)
            cmd = [docker, "stats", container_id, "--no-stream", "--format",
                   '{"cpu":"{{.CPUPerc}}","mem":"{{.MemUsage}}","net":"{{.NetIO}}","block":"{{.BlockIO}}"}']
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                return None

            data = json.loads(res.stdout.strip())
            
            # Parse CPU %
            cpu_str = data.get("cpu", "0%").replace("%", "").strip()
            cpu_percent = float(cpu_str) if cpu_str else 0.0
            
            # Parse memory "1.234MiB / 16GiB"
            mem_str = data.get("mem", "0MiB / 0MiB").split("/")
            mem_usage = _parse_size(mem_str[0].strip()) / (1024 * 1024)
            mem_limit = _parse_size(mem_str[1].strip()) / (1024 * 1024) if len(mem_str) > 1 else 0
            mem_percent = (mem_usage / mem_limit * 100) if mem_limit > 0 else 0
            
            # Parse network "1.2kB / 3.4kB"
            net_str = data.get("net", "0B / 0B").split("/")
            net_in = _parse_size(net_str[0].strip()) if net_str else 0
            net_out = _parse_size(net_str[1].strip()) if len(net_str) > 1 else 0
            
            # Parse block I/O "1.2MB / 3.4MB"
            block_str = data.get("block", "0B / 0B").split("/")
            block_in = _parse_size(block_str[0].strip()) if block_str else 0
            block_out = _parse_size(block_str[1].strip()) if len(block_str) > 1 else 0
            
            return ContainerStats(
                cpu_percent=cpu_percent,
                memory_usage_mb=mem_usage,
                memory_limit_mb=mem_limit,
                memory_percent=mem_percent,
                net_in_bytes=net_in,
                net_out_bytes=net_out,
                block_in_bytes=block_in,
                block_out_bytes=block_out,
            )
        except Exception:
            return None

    def start_container(self, container_id: str) -> tuple[bool, str]:
        """Start a stopped container."""
        docker = self._docker_bin()
        if not docker:
            return False, "Docker introuvable"

        try:
            res = subprocess.run([docker, "start", container_id],
                               capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return True, f"Container {container_id} démarré"
            return False, res.stderr.strip() or "Erreur inconnue"
        except Exception as e:
            return False, str(e)

    def stop_container(self, container_id: str) -> tuple[bool, str]:
        """Stop a running container."""
        docker = self._docker_bin()
        if not docker:
            return False, "Docker introuvable"

        try:
            res = subprocess.run([docker, "stop", container_id],
                               capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return True, f"Container {container_id} arrêté"
            return False, res.stderr.strip() or "Erreur inconnue"
        except Exception as e:
            return False, str(e)

    def inspect_container(self, container_id: str) -> dict[str, Any]:
        """Get full container config (json format)."""
        docker = self._docker_bin()
        if not docker:
            return {}

        try:
            res = subprocess.run([docker, "inspect", container_id],
                               capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return data[0] if data else {}
            return {}
        except Exception:
            return {}


def _parse_size(size_str: str) -> float:
    """Parse size string like '1.2MiB', '3.4kB', etc. to bytes."""
    size_str = size_str.strip().upper()
    if not size_str or size_str == "0" or size_str == "0B":
        return 0.0

    # Order matters: check multi-char units before single 'B' so that e.g.
    # 'MIB' is not matched by the 'B' suffix.
    units = [
        ("GIB", 1024 ** 3),
        ("MIB", 1024 ** 2),
        ("KIB", 1024),
        ("GB", 1000 ** 3),
        ("MB", 1000 ** 2),
        ("KB", 1000),
        ("B", 1),
    ]

    for unit, mult in units:
        if size_str.endswith(unit):
            try:
                num = float(size_str[: -len(unit)].strip())
                return num * mult
            except ValueError:
                return 0.0

    try:
        return float(size_str)
    except ValueError:
        return 0.0


docker_manager = DockerManager()
