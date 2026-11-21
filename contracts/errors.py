"""Shared, bounded error types for TwinLedger contracts and core primitives.

Errors carry a stable machine-readable ``code`` and a public-safe message. They
must never embed sealed data (truth, provenance, seeds, private paths).
"""

from __future__ import annotations

from typing import Any


class TwinLedgerError(Exception):
    """Base class for all TwinLedger errors."""

    code = "TWINLEDGER_ERROR"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": self.context}


class ContractError(TwinLedgerError):
    """Input violates a frozen contract or schema."""

    code = "CONTRACT_VIOLATION"


class ConfigError(TwinLedgerError):
    """Configuration is missing, unknown-version or invalid."""

    code = "CONFIG_INVALID"


class MoneyError(TwinLedgerError):
    """Money arithmetic rejected the input (type, exponent, overflow)."""

    code = "MONEY_INVALID"


class TimeRuleError(TwinLedgerError):
    """Time/period rule rejected the input."""

    code = "TIME_INVALID"


class IdError(TwinLedgerError):
    """Identifier factory rejected the request."""

    code = "ID_INVALID"


class InvariantError(TwinLedgerError):
    """A normative accounting invariant was violated."""

    code = "INVARIANT_VIOLATION"


class RejectError(TwinLedgerError):
    """Episode construction was rejected and cannot be published."""

    code = "EPISODE_REJECTED"


class RejectBudgetExhausted(RejectError):
    """Rejection sampling exhausted its bounded attempt budget."""

    code = "REJECT_BUDGET_EXHAUSTED"


class OperatorError(TwinLedgerError):
    """A mutation operator could not be applied to the given clean twin."""

    code = "OPERATOR_FAILED"
