"""Organizer compatibility profile (master spec §7.3, REQ-ADAPTER-001..004).

Everything that TwinLedger does not know about the organizer contract is isolated here
and in ``configs/adapter/compatibility.json``. Nothing in this module guesses: while the
profile is ``UNBOUND`` every translation entry point raises a bounded
:class:`AdapterNotBound` error instead of silently interpreting an external payload.

Design rules:

* The internal model never changes to match an external field name (REQ-ADAPTER-002).
* There is no silent fallback that treats a malformed external structure as valid
  (REQ-ADAPTER-003).
* Unknown profile versions fail with a bounded error instead of "best effort"
  interpretation (REQ-CONTRACT-022).
* This module imports nothing from ``gen``, ``verifier``, ``scoring``, ``seal`` or
  ``env`` - see docs/DECISIONS.md D-0006 and tools/check_import_boundaries.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "AdapterError",
    "AdapterNotBound",
    "UnsupportedProfileVersion",
    "InvalidExternalPayload",
    "CompatibilityProfile",
    "load_profile",
]

DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "configs" / "adapter" / "compatibility.json"
BOUND = "BOUND"
UNBOUND = "UNBOUND"


class AdapterError(RuntimeError):
    """Base class for bounded adapter failures.

    Messages are safe to surface to a policy: they contain no paths, stack traces or
    sealed content (master spec §14.6).
    """

    code = "ADAPTER_ERROR"


class AdapterNotBound(AdapterError):
    """The organizer contract has not been bound to this repository yet."""

    code = "ADAPTER_NOT_BOUND"

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"organizer contract is not bound; cannot perform {operation}. "
            "See docs/QUESTIONS.md Q-001..Q-014 and docs/ASSUMPTIONS.json."
        )
        self.operation = operation


class UnsupportedProfileVersion(AdapterError):
    """The bound profile declares a version this build cannot interpret."""

    code = "ADAPTER_VERSION_UNSUPPORTED"


class InvalidExternalPayload(AdapterError):
    """The external payload does not match the bound profile."""

    code = "ADAPTER_INVALID_EXTERNAL"


@dataclass(frozen=True)
class CompatibilityProfile:
    """Immutable view of the compatibility profile."""

    profile_id: str
    profile_version: str
    status: str
    supported_versions: frozenset[str]
    tool_aliases: Mapping[str, tuple[str, ...]]
    field_aliases: Mapping[str, tuple[str, ...]]
    unknown_field_policy: str
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def bound(self) -> bool:
        return self.status == BOUND

    def require_bound(self, operation: str) -> None:
        if not self.bound:
            raise AdapterNotBound(operation)

    def internal_tool(self, external_name: str) -> str:
        """Map an external tool name onto the internal tool vocabulary."""
        self.require_bound("tool name mapping")
        for internal, aliases in self.tool_aliases.items():
            if external_name == internal or external_name in aliases:
                return internal
        raise InvalidExternalPayload(f"unknown external tool name {external_name!r}")


def _as_alias_map(raw: Mapping[str, Any], key: str) -> dict[str, tuple[str, ...]]:
    section = raw.get(key, {})
    if not isinstance(section, dict):
        raise AdapterError(f"compatibility profile section {key!r} must be an object")
    out: dict[str, tuple[str, ...]] = {}
    for internal, aliases in section.items():
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            raise AdapterError(f"compatibility alias list for {internal!r} must be strings")
        out[internal] = tuple(aliases)
    return out


def load_profile(path: str | Path | None = None) -> CompatibilityProfile:
    """Load and validate the compatibility profile.

    A profile whose ``profile_version`` is outside ``supported_profile_versions`` is
    rejected with :class:`UnsupportedProfileVersion` - never approximated.
    """
    profile_path = Path(path) if path is not None else DEFAULT_PROFILE_PATH
    raw = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AdapterError("compatibility profile must be a JSON object")

    for required in ("profile_id", "profile_version", "profile_status", "supported_profile_versions"):
        if required not in raw:
            raise AdapterError(f"compatibility profile is missing {required!r}")

    supported = frozenset(str(v) for v in raw["supported_profile_versions"])
    if str(raw["profile_version"]) not in supported:
        raise UnsupportedProfileVersion(
            f"profile version {raw['profile_version']!r} is not supported by this build "
            f"(supported: {sorted(supported)})"
        )

    status = str(raw["profile_status"]).upper()
    if status not in (BOUND, UNBOUND):
        raise AdapterError(f"profile_status must be BOUND or UNBOUND, got {status!r}")

    return CompatibilityProfile(
        profile_id=str(raw["profile_id"]),
        profile_version=str(raw["profile_version"]),
        status=status,
        supported_versions=supported,
        tool_aliases=_as_alias_map(raw, "candidate_tool_aliases"),
        field_aliases=_as_alias_map(raw, "candidate_field_aliases"),
        unknown_field_policy=str(raw.get("unknown_field_policy", "reject")),
        raw=raw,
    )
