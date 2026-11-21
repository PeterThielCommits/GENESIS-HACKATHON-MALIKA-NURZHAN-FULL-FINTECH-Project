"""Contract schema loader (stdlib-only).

Loads ``contracts/*.schema.json`` by short name and validates instances
against them. Unknown schema names raise ``KeyError`` (bounded error,
REQ-CONTRACT-022 style).

Also hosts the shared **bounded input-read guards** used by every
episode-file reader (``env/loader.py``, ``adapter/official_env.py``,
``scoring/official_scorer.py``, ``verifier/public_loader.py``): any file that
comes from an episode directory is read with a hard byte cap and a hard row
cap so an oversized or hostile input can never exhaust memory or stall
startup (review remediation D-10-03).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.validate import validate

_CONTRACTS_DIR = Path(__file__).resolve().parent

#: Hard upper bound on any episode-supplied file read into memory (bytes).
#: Largest measured generated episode public file is ~27 KiB (company size L,
#: 4 anomalies); 16 MiB leaves >500x headroom while fully bounding memory.
MAX_INPUT_FILE_BYTES = 16 * 1024 * 1024

#: Hard upper bound on parsed JSON-object rows per episode-supplied file.
#: Largest measured generated table is 292 rows; README documents a 4 950-row
#: sequential-scan ceiling — 100 000 rows leaves >20x headroom.
MAX_INPUT_ROWS = 100_000

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


def read_text_bounded(path: Path, *, max_bytes: int | None = None) -> str:
    """Read a UTF-8 text file with a hard byte cap.

    Reads at most ``max_bytes + 1`` bytes (default
    :data:`MAX_INPUT_FILE_BYTES`, resolved at call time) so the guard holds
    even if the file grows between checks. Raises ``ValueError`` when the cap
    is exceeded or the content is not valid UTF-8; callers translate that into
    their own bounded error type (``EnvError("LIMIT", ...)``,
    ``PublicEpisodeError``, ...). Never echoes file content in the message.
    """
    cap = MAX_INPUT_FILE_BYTES if max_bytes is None else max_bytes
    if type(cap) is not int or cap < 1:
        raise ValueError("max_bytes must be a positive int")
    with Path(path).open("rb") as fh:
        data = fh.read(cap + 1)
    if len(data) > cap:
        raise ValueError(f"{Path(path).name}: input exceeds size limit of {cap} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{Path(path).name}: input is not valid UTF-8") from exc


def check_row_cap(n_rows: int, name: str, *, max_rows: int | None = None) -> None:
    """Raise ``ValueError`` once ``n_rows`` exceeds :data:`MAX_INPUT_ROWS`.

    The cap is resolved at call time so tests and operators can tighten it by
    patching :data:`MAX_INPUT_ROWS`.
    """
    cap = MAX_INPUT_ROWS if max_rows is None else max_rows
    if type(cap) is not int or cap < 1:
        raise ValueError("max_rows must be a positive int")
    if n_rows > cap:
        raise ValueError(f"{name}: row count exceeds limit of {cap} rows")
