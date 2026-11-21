"""Declared invariant signatures and the error matrix (11.8, 12.3).

Each operator declares:

  intended invariants   — must be violated in the mutated twin;
  allowed side effects  — may be violated as a documented consequence;
  forbidden invariants  — must never be violated (release blocker otherwise).

``verify_signature`` compares the observed violation set against that matrix and
returns a decision plus the exact deltas, so publishable/rejected episodes are
decided by evidence rather than by assumption.

For anomaly types with several documented subtypes the matrix is refined per
subtype: each subtype has an exact, reproducible signature, which is what lets the
independent verifier re-derive the same finding from public data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from contracts.errors import ContractError
from invariants.model import Violation

# Type-level matrix: used when no subtype is declared (and for operators whose
# semantics are single-shaped, e.g. DUPLICATE_PAYMENT).
ERROR_MATRIX: dict[str, dict[str, tuple[str, ...]]] = {
    "DUPLICATE_PAYMENT": {
        # Status is re-derived from public evidence in the mutated twin, so the only
        # *necessary* break is the negative open balance. Subledger drift (INV-03),
        # aging (INV-05) and status drift (INV-17) are documented consequences of an
        # extra settlement, never required.
        "intended": ("INV-04",),
        "allowed": ("INV-03", "INV-05", "INV-17"),
        "forbidden": (
            "INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
            "INV-13", "INV-14", "INV-15", "INV-16",
        ),
    },
    # Type-level union; per-subtype expectations below are authoritative.
    "PARTIAL_PAYMENT_ALLOCATION": {
        "intended": ("INV-04", "INV-15"),
        "allowed": ("INV-03", "INV-05", "INV-17"),
        "forbidden": (
            "INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
            "INV-13", "INV-14", "INV-16",
        ),
    },
}

# Subtype-level matrix (authoritative for these subtypes).
SUBTYPE_MATRIX: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {
    (
        "PARTIAL_PAYMENT_ALLOCATION",
        "OVER_ALLOCATE_TO_ONE_INVOICE",
    ): {
        # One invoice is closed completely although the payment was smaller:
        # allocations exceed the payment (INV-15) AND the document is over-settled
        # (INV-04).
        "intended": ("INV-04", "INV-15"),
        "allowed": ("INV-03", "INV-05", "INV-17"),
        "forbidden": (
            "INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
            "INV-13", "INV-14", "INV-16",
        ),
    },
    (
        "PARTIAL_PAYMENT_ALLOCATION",
        "ALLOCATE_TO_ALREADY_SETTLED_INVOICE",
    ): {
        # Part of a payment is applied to an invoice that was already paid. The
        # payment still conserves (INV-15 stays clean); the only necessary break is
        # the over-paid settled document (INV-04).
        "intended": ("INV-04",),
        "allowed": ("INV-03", "INV-05", "INV-17"),
        "forbidden": (
            "INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
            "INV-13", "INV-14", "INV-16",
        ),
    },
    (
        "PARTIAL_PAYMENT_ALLOCATION",
        "ALLOCATIONS_EXCEED_PAYMENT",
    ): {
        # A payment is spread over two documents for more than the money received.
        # The first document is settled exactly (its remainder often exceeds the
        # payment), so INV-04 need not break: INV-15 is the necessary signature.
        "intended": ("INV-15",),
        "allowed": ("INV-03", "INV-04", "INV-05", "INV-17"),
        "forbidden": (
            "INV-01", "INV-06", "INV-07", "INV-09", "INV-11", "INV-12",
            "INV-13", "INV-14", "INV-16",
        ),
    },
}


@dataclass(frozen=True)
class SignatureDecision:
    """Outcome of comparing observed violations with the declared matrix."""

    anomaly_type: str
    subtype: str | None
    accepted: bool
    reasons: tuple[str, ...]
    observed: tuple[str, ...]
    intended_hit: tuple[str, ...]
    intended_missing: tuple[str, ...]
    forbidden_hit: tuple[str, ...]
    unexpected: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "subtype": self.subtype,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "observed": list(self.observed),
            "intended_hit": list(self.intended_hit),
            "intended_missing": list(self.intended_missing),
            "forbidden_hit": list(self.forbidden_hit),
            "unexpected": list(self.unexpected),
        }


def error_matrix_for(anomaly_type: str, subtype: str | None = None) -> dict[str, tuple[str, ...]]:
    if subtype is not None:
        refined = SUBTYPE_MATRIX.get((anomaly_type, subtype))
        if refined is not None:
            return refined
    matrix = ERROR_MATRIX.get(anomaly_type)
    if matrix is None:
        raise ContractError("unknown anomaly type", anomaly_type=anomaly_type, subtype=subtype)
    return matrix


def verify_signature(
    anomaly_type: str,
    violations: Iterable[Violation],
    *,
    subtype: str | None = None,
    allow_extra: Sequence[str] = (),
) -> SignatureDecision:
    """Compare observed violations with the frozen error matrix."""
    matrix = error_matrix_for(anomaly_type, subtype)
    intended = set(matrix["intended"])
    allowed = set(matrix["allowed"]) | set(allow_extra)
    forbidden = set(matrix["forbidden"])

    observed = tuple(sorted({violation.invariant_id for violation in violations}))
    observed_set = set(observed)

    forbidden_hit = tuple(sorted(observed_set & forbidden))
    intended_hit = tuple(sorted(observed_set & intended))
    intended_missing = tuple(sorted(intended - observed_set))
    unexpected = tuple(sorted(observed_set - intended - allowed - forbidden))

    reasons: list[str] = []
    if forbidden_hit:
        reasons.append(f"forbidden invariants violated: {', '.join(forbidden_hit)}")
    if intended_missing:
        reasons.append(f"intended invariants not violated: {', '.join(intended_missing)}")
    if unexpected:
        reasons.append(f"unexpected violations: {', '.join(unexpected)}")

    return SignatureDecision(
        anomaly_type=anomaly_type,
        subtype=subtype,
        accepted=not reasons,
        reasons=tuple(reasons),
        observed=observed,
        intended_hit=intended_hit,
        intended_missing=intended_missing,
        forbidden_hit=forbidden_hit,
        unexpected=unexpected,
    )
