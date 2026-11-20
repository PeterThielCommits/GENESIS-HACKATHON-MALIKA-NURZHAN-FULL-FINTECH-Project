"""Typed domain models for the contract structures (Phase 1 task 1.4).

Design rules, deliberately strict:

* the **schema is the authority**; a model is a typed mirror, never a second definition. A
  parity tool (`tools/check_models.py`) fails the build if a dataclass field and a schema
  property ever disagree, in either direction;
* construction validates: `from_dict` runs the contract validator first, so an invalid payload
  can never become an object that later code treats as valid;
* `to_dict` emits only the fields that were actually present, so a round-trip of a fixture is
  byte-identical under canonical JSON - no silent defaults invented by the model;
* money stays an integer count of minor units and timestamps stay ISO-8601 UTC strings; the
  models add typing, not semantics.
"""

from __future__ import annotations

import dataclasses
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, TypeVar

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.jsonschema_lite import ContractValidator

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"

T = TypeVar("T", bound="Model")


class ContractViolation(ValueError):
    """Raised when a payload does not satisfy the schema the model mirrors."""


@lru_cache(maxsize=1)
def validator() -> ContractValidator:
    return ContractValidator(CONTRACTS)


@dataclasses.dataclass
class Model:
    """Base class: dataclass fields mirror schema properties one-to-one."""

    SCHEMA: ClassVar[str] = ""
    #: properties the schema marks as required; kept here so `to_dict` can assert completeness
    REQUIRED: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def schema(cls) -> dict:
        import json

        return json.loads((CONTRACTS / cls.SCHEMA).read_text(encoding="utf-8"))

    @classmethod
    def field_names(cls) -> set[str]:
        return {field.name for field in dataclasses.fields(cls)}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue  # absent stays absent: no invented defaults
            if isinstance(value, Model):
                payload[field.name] = value.to_dict()
            elif isinstance(value, list):
                payload[field.name] = [item.to_dict() if isinstance(item, Model) else item
                                       for item in value]
            else:
                payload[field.name] = value
        payload.update(getattr(self, "_extensions", {}))
        return payload

    @classmethod
    def from_dict(cls: type[T], payload: dict[str, Any], *, validate: bool = True) -> T:
        if not isinstance(payload, dict):
            raise ContractViolation(f"{cls.__name__}: payload must be an object")
        if validate:
            problems = validator().validate(payload, cls.SCHEMA)
            if problems:
                detail = "; ".join(str(problem) for problem in problems)
                raise ContractViolation(f"{cls.__name__} violates {cls.SCHEMA}: {detail}")
        known = cls.field_names()
        # The contracts allow forward-compatible extensions under the `x_` prefix. They are
        # carried through untouched - dropping them would corrupt a round-trip and hide data.
        extensions = {key: value for key, value in payload.items()
                      if key.startswith("x_") and key not in known}
        unknown = set(payload) - known - set(extensions)
        if unknown:
            raise ContractViolation(
                f"{cls.__name__} has no field for {sorted(unknown)}; the model would silently "
                f"drop data (fix the model or the schema, not the payload)")
        instance = cls(**{key: value for key, value in payload.items()
                          if key in known})  # type: ignore[arg-type]
        object.__setattr__(instance, "_extensions", extensions)
        return instance

    def validate(self) -> None:
        problems = validator().validate(self.to_dict(), self.SCHEMA)
        if problems:
            detail = "; ".join(str(problem) for problem in problems)
            raise ContractViolation(f"{self.__class__.__name__} is invalid: {detail}")

    def canonical(self) -> dict[str, Any]:
        """Validated, JSON-ready payload (the only form allowed to be hashed or stored)."""
        self.validate()
        return self.to_dict()
