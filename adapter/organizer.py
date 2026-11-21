"""Provisional organiser protocol adapter (TZ 7.3 — Phase 5).

Maps external / legacy organiser payloads onto TwinLedger's frozen v1.0.0
``contracts/`` wire format without modifying any frozen JSON schema.

STATUS: PROVISIONAL (official organiser wire spec pending Q-003..Q-006).
"""

from __future__ import annotations

from typing import Any, Mapping

from contracts.loader import validate_instance
from contracts.models import Finding
from contracts.version import PROTOCOL_VERSION, SCHEMA_VERSION

ADAPTER_PROVISIONAL = True


def normalize_finding(
    raw: Mapping[str, Any],
    *,
    id_namespace_map: Mapping[str, str] | None = None,
) -> Finding:
    """Normalize either a frozen v1.0.0 finding or legacy provisional finding onto ``Finding``.

    Legacy fields supported explicitly:
      - ``amount_minor`` -> ``claimed_amount``
      - untyped IDs when ``id_namespace_map`` provides ``raw_id -> "PREFIX:raw_id"``
      - missing ``schema_version`` defaults to frozen ``"1.0.0"``
    """
    if not isinstance(raw, Mapping):
        raise ValueError("finding payload must be a mapping")

    ns_map = id_namespace_map or {}

    def _norm_ids(values: Any) -> list[str]:
        if not isinstance(values, list):
            raise ValueError("ID list must be a list")
        out: list[str] = []
        for item in values:
            if not isinstance(item, str) or not item:
                raise ValueError(f"invalid ID item: {item!r}")
            out.append(item if ":" in item else ns_map.get(item, item))
        return out

    claimed = raw.get("claimed_amount", raw.get("amount_minor"))
    doc: dict[str, Any] = {
        "schema_version": raw.get("schema_version", SCHEMA_VERSION),
        "type": raw.get("type"),
        "affected_ids": _norm_ids(raw.get("affected_ids")),
        "claimed_amount": claimed,
        "currency": raw.get("currency"),
        "evidence_ids": _norm_ids(raw.get("evidence_ids")),
    }
    if "explanation" in raw and raw["explanation"] is not None:
        doc["explanation"] = raw["explanation"]
    if "confidence" in raw and raw["confidence"] is not None:
        doc["confidence"] = raw["confidence"]

    errs = validate_instance("finding", doc)
    if errs:
        raise ValueError(f"normalized finding failed frozen schema: {errs}")
    return Finding.from_dict(doc)


def normalize_tool_request(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an external tool call dict onto frozen ``contracts/tool_request.schema.json``."""
    if not isinstance(raw, Mapping):
        raise ValueError("tool request must be a mapping")
    if "action" in raw:
        req = {
            "protocol_version": raw.get("protocol_version", PROTOCOL_VERSION),
            "request_id": raw.get("request_id"),
            "action": raw["action"],
        }
    else:
        req = {
            "protocol_version": raw.get("protocol_version", PROTOCOL_VERSION),
            "request_id": raw.get("request_id", "req-0"),
            "action": {"tool": raw.get("tool"), "args": raw.get("args", {})},
        }
    errs = validate_instance("tool_request", req)
    if errs:
        raise ValueError(f"normalized tool_request failed frozen schema: {errs}")
    return req


__all__ = ["ADAPTER_PROVISIONAL", "normalize_finding", "normalize_tool_request"]
