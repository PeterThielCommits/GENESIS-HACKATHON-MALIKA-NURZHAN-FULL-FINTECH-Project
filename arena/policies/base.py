"""Public-only base policy interface for TwinLedger isolated policy workers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePolicy(ABC):
    """Stateful policy interacting strictly via JSON observations and 5 actions."""

    name: str = "base"

    @abstractmethod
    def reset(self, observation: dict[str, Any]) -> None:
        """Initialize policy state from the first public observation."""

    @abstractmethod
    def act(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Return the next action envelope ``{"name": ..., "args": ...}``."""


__all__ = ["BasePolicy"]
