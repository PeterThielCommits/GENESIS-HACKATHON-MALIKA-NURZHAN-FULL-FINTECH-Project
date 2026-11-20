"""Contract schema loader (stdlib-only).

Loads ``contracts/*.schema.json`` by short name and validates instances
against them. Unknown schema names raise ``KeyError`` (bounded error,
REQ-CONTRACT-022 style).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.validate import validate

_CONTRACTS_DIR = Path(__file__).resolve().parent

SCHEMA_FILES: dict[str, str] = {
    "episode_manifest": "episode_manifest.schema.json",
    "company": "company.schema.json",
    "policy": "policy.schema.json",
    "finding": "finding.schema.json",
    "truth": "truth.schema.json",
    "tool_request": "tool_request.schema.json",
    "tool_response": "tool_response.schema.json",
    "trajectory_event": "trajectory_event.schema.json",
    "receipt": "receipt.schema.json",
    "verifier_report": "verifier_report.schema.json",
    "rubric_check": "rubric_check.schema.json",
    "config": "config.schema.json",
}

_cache: dict[str, dict[str, Any]] = {}


def load_schema(name: str) -> dict[str, Any]:
    """Load a contract schema by short name (e.g. ``"finding"``)."""
    if name not in SCHEMA_FILES:
        raise KeyError(f"unknown contract schema: {name!r}")
    if name not in _cache:
        path = _CONTRACTS_DIR / SCHEMA_FILES[name]
        _cache[name] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[name]


def validate_instance(name: str, instance: Any) -> list[str]:
    """Validate ``instance`` against contract ``name``. Returns errors."""
    return validate(instance, load_schema(name))


def load_version() -> dict[str, Any]:
    path = _CONTRACTS_DIR / "version.json"
    return json.loads(path.read_text(encoding="utf-8"))
