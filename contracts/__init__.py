"""TwinLedger contracts package (frozen for MVP, Phase 1).

Single source of truth for public schemas, canonical JSON and typed
models. All modules may import from here (TZ section 6).
"""

from contracts.canonical import (
    canonical_bytes,
    canonical_json,
    canonicalize,
    config_hash,
    parse_canonical,
    sha256_bytes,
    sha256_hex,
)
from contracts.loader import load_schema, load_version, validate_instance
from contracts.models import (
    Finding,
    Receipt,
    ToolRequest,
    ToolResponse,
    TrajectoryEvent,
    TruthFinding,
    canonical_ids,
)
from contracts.validate import is_valid, validate
from contracts.version import CONTRACT_VERSION, PROTOCOL_VERSION, SCHEMA_VERSION

__all__ = [
    "CONTRACT_VERSION", "SCHEMA_VERSION", "PROTOCOL_VERSION",
    "canonical_json", "canonical_bytes", "canonicalize", "config_hash",
    "sha256_hex", "sha256_bytes", "parse_canonical",
    "load_schema", "load_version", "validate_instance", "validate", "is_valid",
    "Finding", "ToolRequest", "ToolResponse", "TrajectoryEvent",
    "Receipt", "TruthFinding", "canonical_ids",
]
