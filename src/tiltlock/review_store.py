"""Persist the latest review so `tiltlock ask` can answer without rerunning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from tiltlock.config import AppConfig
from tiltlock.models import TiltDiagnosis


def _path() -> Path:
    path = AppConfig.find_repo_root() / "state" / "last_review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_review(diagnosis: TiltDiagnosis, extra: Optional[Dict[str, Any]] = None) -> None:
    payload = diagnosis.model_dump()
    if extra:
        payload["context"] = extra
    _path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_review() -> Optional[Dict[str, Any]]:
    path = _path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
