"""TwinLedger independent re-derivation verifier (second implementation).

A from-scratch, specification-only implementation of the same checks the
primary ``verifier`` package performs. It exists to provide *organisational
independence evidence*: if two implementations derived from the same frozen
specification agree on public episode data, the findings are much harder to
dismiss as generator artifacts.

Boundaries (identical to the primary verifier):
  - Public episode data only (``public/``); never reads ``hidden/``.
  - Never imports the generator (``gen``) or environment/truth code.
  - Money is integer minor units; FX via exact fixed-point rationals only.
  - No wall-clock time, no randomness, no network.
"""

INDEPENDENT_VERIFIER_VERSION = "independent-1.0.0"
