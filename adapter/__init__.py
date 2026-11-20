"""Organizer adapter boundary.

Only this package is allowed to know about external (organizer) field names, tool names
and envelope shapes. Internal modules speak the TwinLedger contracts in ``contracts/``.

Phase 0 status: the organizer contract is UNBOUND, so every translation entry point
raises a bounded adapter error instead of guessing (see docs/ASSUMPTIONS.json).
"""

from adapter.compatibility import (
    AdapterError,
    AdapterNotBound,
    CompatibilityProfile,
    InvalidExternalPayload,
    UnsupportedProfileVersion,
    load_profile,
)

__all__ = [
    "AdapterError",
    "AdapterNotBound",
    "CompatibilityProfile",
    "InvalidExternalPayload",
    "UnsupportedProfileVersion",
    "load_profile",
]
