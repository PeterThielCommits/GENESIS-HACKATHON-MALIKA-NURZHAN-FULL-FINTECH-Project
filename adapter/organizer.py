"""Official protocol adapter interface (master spec §7.3).

The four functions below are the *only* allowed crossing point between external
organizer payloads and the internal canonical contracts:

    normalize_request(external_request)   -> InternalAction | ContractError
    serialize_observation(internal_result) -> external_response
    normalize_finding(external_finding)   -> CanonicalFinding | ContractError
    serialize_submission(internal_findings) -> external_submission

Phase 0 deliberately ships them as explicitly unbound entry points: the organizer schemas
have not been published to this repository (docs/QUESTIONS.md Q-001..Q-014). Raising a
bounded error is correct behaviour - a silent fallback would violate REQ-ADAPTER-003.
"""

from __future__ import annotations

from typing import Any, Mapping

from adapter.compatibility import (
    AdapterError,
    AdapterNotBound,
    CompatibilityProfile,
    InvalidExternalPayload,
    load_profile,
)

__all__ = [
    "normalize_request",
    "serialize_observation",
    "normalize_finding",
    "serialize_submission",
    "AdapterError",
    "AdapterNotBound",
    "InvalidExternalPayload",
]

_INTERNAL_TOOLS = ("list_records", "get_record", "get_document", "calc", "submit")
_INTERNAL_FINDING_FIELDS = (
    "type",
    "affected_ids",
    "claimed_amount",
    "currency",
    "evidence_ids",
    "explanation",
    "confidence",
)


def normalize_request(external_request: Mapping[str, Any], profile: CompatibilityProfile | None = None) -> dict:
    """Translate an external tool request into the internal ``tool_request`` contract."""
    profile = profile or load_profile()
    profile.require_bound("normalize_request")
    # Reached only when a real profile is bound; the mapping below is the reviewed shape.
    if not isinstance(external_request, Mapping):
        raise InvalidExternalPayload("external request must be an object")
    action = external_request.get("action")
    if not isinstance(action, Mapping):
        raise InvalidExternalPayload("external request has no action object")
    tool = profile.internal_tool(str(action.get("tool", "")))
    if tool not in _INTERNAL_TOOLS:
        raise InvalidExternalPayload("tool is outside the internal allowlist")
    return {"schema_version": "1.0.0", "request_id": str(external_request.get("request_id", "")),
            "action": {"tool": tool, "args": dict(action.get("args") or {})}}


def serialize_observation(internal_result: Mapping[str, Any], profile: CompatibilityProfile | None = None) -> dict:
    """Translate an internal ``tool_response`` into the external response envelope."""
    profile = profile or load_profile()
    profile.require_bound("serialize_observation")
    raise InvalidExternalPayload("bound profile does not define an observation envelope mapping yet")


def normalize_finding(external_finding: Mapping[str, Any], profile: CompatibilityProfile | None = None) -> dict:
    """Translate an external finding into the canonical ``finding`` contract."""
    profile = profile or load_profile()
    profile.require_bound("normalize_finding")
    if not isinstance(external_finding, Mapping):
        raise InvalidExternalPayload("external finding must be an object")
    unknown = set(external_finding) - set(_INTERNAL_FINDING_FIELDS) - {"x_twinledger_policy"}
    if unknown:
        raise InvalidExternalPayload(f"unknown finding fields: {sorted(unknown)}")
    return dict(external_finding)


def serialize_submission(internal_findings: list[Mapping[str, Any]],
                         profile: CompatibilityProfile | None = None) -> dict:
    """Translate canonical findings into the external submission document."""
    profile = profile or load_profile()
    profile.require_bound("serialize_submission")
    raise InvalidExternalPayload("bound profile does not define a submission envelope mapping yet")
