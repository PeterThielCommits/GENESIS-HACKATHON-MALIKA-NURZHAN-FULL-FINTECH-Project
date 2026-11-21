"""Common mutation-operator interface (11.1, REQ-ERR-001..005).

Contract every operator must satisfy:

* ``apply_book`` never mutates the clean twin; it returns a new ``Book``;
* the operator is deterministic on ``(book, params)`` — randomness, when needed,
  comes from an explicitly injected ``RngStream`` under ``mutation/...``;
* it declares which invariants it *intends* to break, which side effects are
  allowed and which are forbidden (11.8 error matrix);
* it records the affected ids by its documented rule, and the causal delta is
  measured between the pre- and post-state digests (11.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from contracts.canonical import digest_of
from contracts.errors import OperatorError
from gen.core.rng import RngStream
from gen.twins import Book


@dataclass(frozen=True)
class OperatorSpec:
    operator_id: str
    operator_version: str
    anomaly_type: str
    intended_invariants: tuple[str, ...]
    allowed_side_effects: tuple[str, ...]
    forbidden_invariants: tuple[str, ...]
    supported_policy_profiles: tuple[str, ...]
    anomalies_created: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "operator_version": self.operator_version,
            "anomaly_type": self.anomaly_type,
            "intended_invariants": list(self.intended_invariants),
            "allowed_side_effects": list(self.allowed_side_effects),
            "forbidden_invariants": list(self.forbidden_invariants),
            "supported_policy_profiles": list(self.supported_policy_profiles),
            "anomalies_created": self.anomalies_created,
        }


@dataclass(frozen=True)
class OperatorApplication:
    """Deterministic record of one applied (or rejected) operator."""

    operator_id: str
    operator_version: str
    params: Mapping[str, Any]
    affected_ids: tuple[str, ...]
    pre_state_digest: str
    post_state_digest: str
    status: str = "APPLIED"
    reject_reason: str | None = None
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    def to_provenance(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "operator_version": self.operator_version,
            "params": dict(self.params),
            "affected_ids": list(self.affected_ids),
            "pre_state_digest": self.pre_state_digest,
            "post_state_digest": self.post_state_digest,
            "status": self.status,
            **({"reject_reason": self.reject_reason} if self.reject_reason else {}),
        }


class MutationOperator:
    """Base class for counterfactual mutation operators."""

    spec: OperatorSpec

    # ------------------------------------------------------------------ contract
    def preconditions(self, book: Book, params: Mapping[str, Any]) -> None:
        """Raise ``OperatorError`` when the operator cannot be applied."""
        raise NotImplementedError

    def apply_book(self, book: Book, params: Mapping[str, Any], rng: RngStream) -> Book:
        """Return a *new* book with the mutation applied; never mutate ``book``."""
        raise NotImplementedError

    def affected_ids(self, book_before: Book, book_after: Book, params: Mapping[str, Any]) -> tuple[str, ...]:
        raise NotImplementedError

    def candidate_params(self, book: Book, config: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Enumerate parameter sets that satisfy the preconditions.

        Deterministic: the order depends only on ``book`` and ``config``. The
        episode builder uses this list for rejection sampling, so a seed without a
        valid candidate is rejected instead of producing a half-valid episode
        (REQ-GEN-020).
        """
        raise NotImplementedError

    def selection_table(
        self,
        candidates: Sequence[Mapping[str, Any]],
        config: Mapping[str, Any],
    ) -> tuple[str, dict[str, int]] | None:
        """Optional weighted selection over a candidate field.

        Operators with documented subtypes return ``(field, weights)`` so the episode
        builder can honour configured proportions instead of letting the first entry
        of a grouped candidate list dominate every episode.
        """
        return None

    def expected_signature(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Declared invariant signature (compared with observed violations)."""
        return {
            "anomaly_type": self.spec.anomaly_type,
            "intended_invariants": list(self.spec.intended_invariants),
            "allowed_side_effects": list(self.spec.allowed_side_effects),
            "affected_ids": list(params.get("expected_affected_ids", ())),
        }

    # ------------------------------------------------------------------- helper
    def apply(
        self, book: Book, params: Mapping[str, Any], rng: RngStream
    ) -> tuple[Book, OperatorApplication]:
        """Validate, apply and record one operator application."""
        self.preconditions(book, params)
        pre_digest = digest_of(book.public_files())
        mutated = self.apply_book(book, params, rng)
        if mutated is book:
            raise OperatorError(
                "operator returned the same book object; a new snapshot is required",
                operator=self.spec.operator_id,
            )
        post_digest = digest_of(mutated.public_files())
        if post_digest == pre_digest:
            raise OperatorError(
                "operator produced no structural change",
                operator=self.spec.operator_id,
            )
        affected = self.affected_ids(book, mutated, params)
        if not affected:
            raise OperatorError(
                "operator produced no affected ids", operator=self.spec.operator_id
            )
        application = OperatorApplication(
            operator_id=self.spec.operator_id,
            operator_version=self.spec.operator_version,
            params=dict(params),
            affected_ids=affected,
            pre_state_digest=pre_digest,
            post_state_digest=post_digest,
        )
        return mutated, application


def require_keys(params: Mapping[str, Any], required: Sequence[str], *, operator: str) -> None:
    missing = [key for key in required if key not in params]
    if missing:
        raise OperatorError("operator params missing keys", operator=operator, missing=missing)


def reject(application_reason: str, *, operator: str) -> None:
    raise OperatorError(application_reason, operator=operator)
