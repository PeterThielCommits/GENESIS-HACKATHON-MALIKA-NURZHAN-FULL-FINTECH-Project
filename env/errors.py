"""Bounded error taxonomy matching frozen ``contracts/tool_response.schema.json``."""

from __future__ import annotations

VALID_ERROR_CODES = frozenset(
    {
        "UNKNOWN_TOOL",
        "BAD_ARGS",
        "BAD_FILTER",
        "BAD_CURSOR",
        "NOT_FOUND",
        "BAD_FINDING",
        "CALC_ERROR",
        "LIMIT",
        "TERMINATED",
        "ALREADY_SUBMITTED",
        "INTERNAL",
    }
)


class EnvError(Exception):
    """Structured bounded environment error (never leaks private state)."""

    def __init__(self, code: str, message: str) -> None:
        if code not in VALID_ERROR_CODES:
            raise ValueError(f"unsupported EnvError code: {code!r}")
        self.code = code
        self.message = str(message)[:500]
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


__all__ = ["EnvError", "VALID_ERROR_CODES"]
