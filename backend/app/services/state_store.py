"""Tiny JSON-file state persistence shared between the API and subprocesses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


def _path(name: str) -> Path:
    return settings.state_dir / f"{name}.json"


def load_state(name: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    p = _path(name)
    if not p.exists():
        return dict(default or {})
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(default or {})


def save_state(name: str, data: dict[str, Any]) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    _path(name).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                          encoding="utf-8")
