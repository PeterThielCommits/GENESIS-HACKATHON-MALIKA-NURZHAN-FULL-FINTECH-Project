"""Contract version constants (frozen for MVP in Phase 1).

Bump rules (TZ 7.1):
  - incompatible change -> major version bump
  - new optional field  -> minor version bump
  - description fix only -> patch version bump
"""

from __future__ import annotations

CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
PROTOCOL_VERSION = "1.0"
GENERATOR_VERSION = "0.1.0"
VERIFIER_VERSION = "0.1.0"
SCORING_VERSION = "0.1.0"
ENV_VERSION = "0.1.0"
HARNESS_VERSION = "0.1.0"
