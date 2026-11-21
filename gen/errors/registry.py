"""Operator registry: the single source of truth for Phase 4 anomaly families.

Every operator must be registered here before it can be selected by
``gen/build_episodes.py``. Registration validates the operator's declared signature
against the frozen anomaly catalogue, so an operator cannot claim invariants that the
catalogue does not grant it (12.x error matrix, 10.3).

Adding a family in a later phase means: implement ``MutationOperator``, list it in
``_FACTORIES``, and extend ``contracts/anomaly_catalog.json`` in the same commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Iterable, Mapping

from contracts.errors import ConfigError, OperatorError
from gen.errors.base import MutationOperator, OperatorSpec
from gen.errors.duplicate_payment import DuplicatePaymentOperator
from gen.errors.partial_allocation import SUBTYPES as PARTIAL_SUBTYPES
from gen.errors.partial_allocation import PartialAllocationOperator

ANOMALY_DUPLICATE_PAYMENT: Final[str] = "DUPLICATE_PAYMENT"
ANOMALY_PARTIAL_ALLOCATION: Final[str] = "PARTIAL_PAYMENT_ALLOCATION"

_FACTORIES: Final[dict[str, type[MutationOperator]]] = {
    "OP-DUPLICATE_PAYMENT": DuplicatePaymentOperator,
    "OP-PARTIAL_PAYMENT_ALLOCATION": PartialAllocationOperator,
}

#: Anomaly families the registry is expected to expose. Phase 4 requires two.
REQUIRED_ANOMALY_TYPES: Final[tuple[str, ...]] = (
    ANOMALY_DUPLICATE_PAYMENT,
    ANOMALY_PARTIAL_ALLOCATION,
)


@dataclass(frozen=True)
class RegistryEntry:
    """One registered operator plus the catalogue facts it is allowed to use."""

    operator_id: str
    operator_version: str
    anomaly_type: str
    intended_invariants: tuple[str, ...]
    allowed_side_effects: tuple[str, ...]
    forbidden_invariants: tuple[str, ...]
    subtypes: tuple[str, ...]
    factory: type[MutationOperator]

    @property
    def spec(self) -> OperatorSpec:
        return self.factory().spec

    def describe(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "operator_version": self.operator_version,
            "anomaly_type": self.anomaly_type,
            "intended_invariants": list(self.intended_invariants),
            "allowed_side_effects": list(self.allowed_side_effects),
            "forbidden_invariants": list(self.forbidden_invariants),
            "subtypes": list(self.subtypes),
        }


def _registry() -> dict[str, RegistryEntry]:
    entries: dict[str, RegistryEntry] = {}
    for operator_id, factory in _FACTORIES.items():
        spec = factory().spec
        if spec.operator_id != operator_id:
            raise OperatorError(
                "operator spec id does not match its registry key",
                key=operator_id,
                spec=spec.operator_id,
            )
        subtypes: tuple[str, ...] = ()
        if operator_id == "OP-PARTIAL_PAYMENT_ALLOCATION":
            subtypes = tuple(PARTIAL_SUBTYPES)
        entries[operator_id] = RegistryEntry(
            operator_id=operator_id,
            operator_version=spec.operator_version,
            anomaly_type=spec.anomaly_type,
            intended_invariants=tuple(spec.intended_invariants),
            allowed_side_effects=tuple(spec.allowed_side_effects),
            forbidden_invariants=tuple(spec.forbidden_invariants),
            subtypes=subtypes,
            factory=factory,
        )
    return entries


_REGISTRY: Final[dict[str, RegistryEntry]] = _registry()


def all_entries() -> tuple[RegistryEntry, ...]:
    """Every registered operator, in stable id order."""
    return tuple(_REGISTRY[key] for key in sorted(_REGISTRY))


def get(operator_id: str) -> RegistryEntry:
    entry = _REGISTRY.get(operator_id)
    if entry is None:
        raise OperatorError(
            "operator is not registered", operator_id=operator_id, known=sorted(_REGISTRY)
        )
    return entry


def operator_ids() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def anomaly_types() -> tuple[str, ...]:
    return tuple(sorted({entry.anomaly_type for entry in all_entries()}))


def factory_for(operator_id: str) -> type[MutationOperator]:
    return get(operator_id).factory


def required_anomaly_types_present() -> bool:
    """Phase 4 gate: both anomaly families must be registered."""
    return set(REQUIRED_ANOMALY_TYPES) <= set(anomaly_types())


def validate_against_catalogue(catalogue: Mapping[str, Any]) -> list[str]:
    """Check the registry against ``contracts/anomaly_catalog.json``.

    Returns a list of human-readable problems (empty means consistent). This is a
    configuration check, not a business rule: it catches the classic drift where an
    operator is coded to violate an invariant the catalogue forbids.
    """
    problems: list[str] = []
    families = catalogue.get("types")
    if not isinstance(families, list):
        return ["anomaly catalogue has no 'types' list"]
    by_type = {str(item.get("type")): item for item in families if isinstance(item, Mapping)}
    for entry in all_entries():
        family = by_type.get(entry.anomaly_type)
        if family is None:
            problems.append(f"{entry.anomaly_type}: missing from anomaly catalogue")
            continue
        intended = set(_as_set(family.get("intended_invariants")))
        allowed = set(_as_set(family.get("allowed_side_effects")))
        forbidden = set(_as_set(family.get("forbidden_invariants")))
        if set(entry.intended_invariants) != intended:
            problems.append(
                f"{entry.anomaly_type}: intended mismatch "
                f"registry={sorted(entry.intended_invariants)} catalogue={sorted(intended)}"
            )
        if set(entry.allowed_side_effects) != allowed:
            problems.append(
                f"{entry.anomaly_type}: allowed side effects mismatch "
                f"registry={sorted(entry.allowed_side_effects)} catalogue={sorted(allowed)}"
            )
        if set(entry.forbidden_invariants) != forbidden:
            problems.append(
                f"{entry.anomaly_type}: forbidden mismatch "
                f"registry={sorted(entry.forbidden_invariants)} catalogue={sorted(forbidden)}"
            )
        overlap = intended & forbidden
        if overlap:
            problems.append(f"{entry.anomaly_type}: invariants both intended and forbidden {sorted(overlap)}")
        if entry.subtypes:
            declared = set(_as_set(family.get("subtypes")))
            missing = set(entry.subtypes) - declared if declared else set()
            if missing:
                problems.append(f"{entry.anomaly_type}: subtypes missing from catalogue {sorted(missing)}")
    return problems


def _as_set(value: Any) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item) for item in value)
    raise ConfigError("catalogue field must be a list", value_type=type(value).__name__)


__all__ = [
    "ANOMALY_DUPLICATE_PAYMENT",
    "ANOMALY_PARTIAL_ALLOCATION",
    "REQUIRED_ANOMALY_TYPES",
    "RegistryEntry",
    "all_entries",
    "anomaly_types",
    "factory_for",
    "get",
    "operator_ids",
    "required_anomaly_types_present",
    "validate_against_catalogue",
]
