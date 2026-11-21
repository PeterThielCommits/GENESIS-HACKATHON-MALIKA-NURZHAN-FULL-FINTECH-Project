"""Bounded rejection sampling for episode construction (Phase 4.7, 10.4).

An episode is **not published** if any hard gate fails. Sampling retries only the
mutation namespace (never the clean history), has a bounded attempt budget, and
raises ``REJECT_BUDGET_EXHAUSTED`` rather than emitting a half-valid episode
(REQ-GEN-020..022).

Determinism: the attempt sequence is a pure function of
``(master_seed, config_hash, difficulty, operator index)``, so the same seed and
config produce the same number of attempts and the same rejection reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence, TypeVar

from contracts.errors import ConfigError, RejectBudgetExhausted, RejectError

T = TypeVar("T")

# Frozen reason codes: used in reports, never containing private ids.
REJECT_REASONS: tuple[str, ...] = (
    "CLEAN_TWIN_INVARIANT_VIOLATION",
    "NO_CANDIDATE_PARAMS",
    "OPERATOR_PRECONDITION_FAILED",
    "OPERATOR_APPLICATION_FAILED",
    "SIGNATURE_MISMATCH",
    "UNREACHABLE_EVIDENCE",
    "DIFF_INCONSISTENT",
    "CLEAN_TWIN_MUTATED",
    "DUPLICATE_AFFECTED_IDS",
    "AMBIGUOUS_FINDINGS",
)


@dataclass
class RejectLog:
    """Aggregated, seed-free statistics of one episode's sampling run."""

    attempts: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    accepted: bool = False
    attempt_trace: list[str] = field(default_factory=list)

    def record(self, reason: str) -> None:
        if reason not in REJECT_REASONS:
            raise ConfigError("unknown reject reason code", reason=reason)
        self.attempts += 1
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1
        self.attempt_trace.append(f"attempt {self.attempts}: {reason}")

    def to_stats(self) -> dict[str, Any]:
        return {
            "attempts": self.attempts,
            "accepted": self.accepted,
            "by_reason": dict(sorted(self.by_reason.items())),
        }


class Rejected(RejectError):
    """A single attempt failed a hard gate and may be retried."""

    def __init__(self, reason: str, **context: Any) -> None:
        if reason not in REJECT_REASONS:
            raise ConfigError("unknown reject reason code", reason=reason)
        super().__init__("episode attempt rejected", reason=reason, **context)
        self.reason = reason


def reject(reason_code: str, **context: Any) -> None:
    """Raise a retryable rejection with a frozen reason code."""
    raise Rejected(reason_code, **context)


def sample(
    *,
    attempt: Callable[[int], T],
    limit: int,
    log: RejectLog,
) -> T:
    """Run ``attempt`` until it succeeds or the budget is exhausted."""
    if limit < 1:
        raise ConfigError("rejection budget must be >= 1", limit=limit)
    last_error: Rejected | None = None
    for index in range(limit):
        try:
            value = attempt(index)
        except Rejected as exc:
            log.record(exc.reason)
            last_error = exc
            continue
        log.accepted = True
        return value
    log.accepted = False
    raise RejectBudgetExhausted(
        "rejection sampling exhausted its budget",
        attempts=limit,
        by_reason=dict(sorted(log.by_reason.items())),
        last_reason=None if last_error is None else last_error.reason,
    )


def assert_distinct_affected_ids(
    findings: Sequence[Mapping[str, Any]],
) -> None:
    """Two findings may not share the same affected-id signature (11.7 ambiguity)."""
    seen: dict[tuple[str, ...], int] = {}
    for index, finding in enumerate(findings):
        key = tuple(sorted(str(item) for item in finding.get("affected_ids", ())))
        if key in seen:
            raise Rejected(
                "AMBIGUOUS_FINDINGS",
                first=seen[key],
                second=index,
                affected_ids=list(key),
            )
        seen[key] = index
