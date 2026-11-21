"""Canonical typed IDs and boundary validation for the scorer.

Implements Master TZ v3.0.0 section 15.1 (canonicalisation) and tasks
6.1/6.2 of Phase 6:

  - every ID is a typed string ``<NAMESPACE>:<local>`` (frozen finding
    schema v1.0.0, ``contracts/finding.schema.json``);
  - IDs are Unicode NFC-normalised, namespace-checked, sorted and
    deduplicated; prefixes are never stripped (that could collide);
  - an unknown namespace or an ambiguous/malformed ID makes the finding
    invalid (``ScoringInputError``), never silently repaired;
  - all scorer inputs are validated at the module boundary against the
    frozen schemas (REQ-CONTRACT-002).

This module is the single place the scorer canonicalises IDs; the match
predicate and the matching algorithm consume its output. Stdlib-only and
restricted to ``contracts`` imports (TZ 6 import rules for ``scoring/``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Sequence

from contracts.loader import validate_instance
from contracts.models import Finding, TruthFinding

#: Typed-ID namespaces of the frozen contracts (finding/truth schemas).
NAMESPACES: tuple[str, ...] = ("JE", "INV", "CN", "PAY", "BANK", "FX", "CP")

_TYPED_ID_RE = re.compile(r"^(JE|INV|CN|PAY|BANK|FX|CP):([A-Za-z0-9._/-]+)$")

#: Schema caps (``finding.schema.json`` / ``truth.schema.json``).
MAX_AFFECTED_IDS = 20
MAX_EVIDENCE_IDS = 20
MAX_EVIDENCE_SETS = 32


class ScoringInputError(ValueError):
    """Raised when scorer input violates the frozen contracts.

    The message names the offending index/field and the exact reason; it
    never includes hidden truth metadata beyond the provided input.
    """


def parse_typed_id(raw: str) -> tuple[str, str]:
    """Return ``(namespace, local)`` for one typed ID.

    Steps (TZ 15.1): Unicode NFC normalisation first, then namespace and
    shape validation. Raises :class:`ScoringInputError` for unknown
    namespaces, empty local parts and ambiguous shapes (e.g. a second
    colon in the local part).
    """
    if not isinstance(raw, str):
        raise ScoringInputError(f"typed ID must be str, got {type(raw).__name__}")
    norm = unicodedata.normalize("NFC", raw)
    match = _TYPED_ID_RE.match(norm)
    if match is None:
        if ":" not in norm:
            raise ScoringInputError(f"typed ID missing namespace prefix: {raw!r}")
        namespace, _, local = norm.partition(":")
        if namespace not in NAMESPACES:
            raise ScoringInputError(
                f"unknown typed-ID namespace {namespace!r} in {raw!r}; "
                f"expected one of {', '.join(NAMESPACES)}"
            )
        raise ScoringInputError(
            f"typed ID {raw!r} is malformed or ambiguous "
            f"(local part must match [A-Za-z0-9._/-]+ and contain no ':')"
        )
    return match.group(1), match.group(2)


def canonical_id(raw: str) -> str:
    """Canonical string form of one typed ID: ``<NAMESPACE>:<local>``."""
    namespace, local = parse_typed_id(raw)
    return f"{namespace}:{local}"


def canonical_id_set(ids: Iterable[str]) -> tuple[str, ...]:
    """Canonicalise an ID collection: NFC, validate, dedupe, sort.

    The result is a sorted tuple of canonical IDs; because the namespace
    stays part of the string, distinct namespaces can never collide
    (TZ 15.1: prefixes are not stripped).
    """
    canonical: set[str] = set()
    for raw in ids:
        canonical.add(canonical_id(raw))
    return tuple(sorted(canonical))


def _check_id_list(
    ids: Any, field: str, index: int | None, max_items: int
) -> tuple[str, ...]:
    where = f"finding[{index}].{field}" if index is not None else field
    if not isinstance(ids, (list, tuple)):
        raise ScoringInputError(f"{where}: expected a list of typed IDs")
    if len(ids) < 1:
        raise ScoringInputError(f"{where}: at least one typed ID is required")
    if len(ids) > max_items:
        raise ScoringInputError(f"{where}: at most {max_items} typed IDs allowed")
    try:
        return canonical_id_set(ids)
    except ScoringInputError as exc:
        raise ScoringInputError(f"{where}: {exc}") from exc


def _check_money_int(value: Any, field: str, index: int | None) -> int:
    where = f"finding[{index}].{field}" if index is not None else field
    if type(value) is not int:
        raise ScoringInputError(
            f"{where}: expected int minor units, got {type(value).__name__}"
        )
    if not -(2**63) <= value < 2**63:
        raise ScoringInputError(f"{where}: value outside signed int64 minor units")
    return value


def canonicalize_finding(finding: Finding) -> Finding:
    """Validate one finding against the frozen schema and canonicalise it.

    Returns a new :class:`Finding` whose ``affected_ids`` and
    ``evidence_ids`` are canonical sorted tuples. Structural violations
    raise :class:`ScoringInputError` (REQ-CONTRACT-002); the canonical
    result then re-validates against the schema round-trip.
    """
    errors = validate_instance("finding", finding.to_dict())
    if errors:
        raise ScoringInputError(f"finding violates frozen schema: {'; '.join(errors)}")
    affected = _check_id_list(finding.affected_ids, "affected_ids", None, MAX_AFFECTED_IDS)
    evidence = _check_id_list(finding.evidence_ids, "evidence_ids", None, MAX_EVIDENCE_IDS)
    _check_money_int(finding.claimed_amount, "claimed_amount", None)
    return Finding(
        type=finding.type,
        affected_ids=affected,
        claimed_amount=finding.claimed_amount,
        currency=finding.currency,
        evidence_ids=evidence,
        explanation=finding.explanation,
        confidence=finding.confidence,
        schema_version=finding.schema_version,
    )


def canonicalize_truth(truth: TruthFinding) -> TruthFinding:
    """Validate one sealed truth finding and canonicalise its ID sets."""
    errors = validate_instance("truth", truth.to_dict())
    if errors:
        raise ScoringInputError(f"truth violates frozen schema: {'; '.join(errors)}")
    affected = canonical_id_set(truth.affected_ids)
    evidence_sets: list[tuple[str, ...]] = []
    if not truth.evidence_sets:
        raise ScoringInputError("truth.evidence_sets: at least one evidence set required")
    if len(truth.evidence_sets) > MAX_EVIDENCE_SETS:
        raise ScoringInputError(f"truth.evidence_sets: at most {MAX_EVIDENCE_SETS} sets allowed")
    for raw_set in truth.evidence_sets:
        canonical_set = _check_id_list(
            raw_set, "evidence_sets[]", None, MAX_EVIDENCE_IDS
        )
        evidence_sets.append(canonical_set)
    if type(truth.amount_minor) is not int:
        raise ScoringInputError("truth.amount_minor: expected int minor units")
    if type(truth.tolerance_minor) is not int or truth.tolerance_minor < 0:
        raise ScoringInputError("truth.tolerance_minor: expected non-negative int minor units")
    return TruthFinding(
        truth_id=truth.truth_id,
        type=truth.type,
        affected_ids=affected,
        amount_minor=truth.amount_minor,
        currency=truth.currency,
        tolerance_minor=truth.tolerance_minor,
        evidence_sets=tuple(evidence_sets),
        minimal_evidence_size=truth.minimal_evidence_size,
        invariant_signature=dict(truth.invariant_signature),
        operator_version=truth.operator_version,
        evidence_enumeration_complete=truth.evidence_enumeration_complete,
        optimal_steps_model_id=truth.optimal_steps_model_id,
        optimal_steps=truth.optimal_steps,
        depends_on=truth.depends_on,
        schema_version=truth.schema_version,
    )


def validate_findings(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    """Validate and canonicalise a submitted finding list (strict boundary)."""
    out: list[Finding] = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, Finding):
            raise ScoringInputError(
                f"finding[{index}]: expected Finding, got {type(finding).__name__}"
            )
        try:
            out.append(canonicalize_finding(finding))
        except ScoringInputError as exc:
            raise ScoringInputError(f"finding[{index}]: {exc}") from exc
    return tuple(out)


def validate_truths(truths: Sequence[TruthFinding]) -> tuple[TruthFinding, ...]:
    """Validate and canonicalise the sealed truth list (strict boundary)."""
    out: list[TruthFinding] = []
    for index, truth in enumerate(truths):
        if not isinstance(truth, TruthFinding):
            raise ScoringInputError(
                f"truth[{index}]: expected TruthFinding, got {type(truth).__name__}"
            )
        try:
            out.append(canonicalize_truth(truth))
        except ScoringInputError as exc:
            raise ScoringInputError(f"truth[{index}]: {exc}") from exc
    return tuple(out)


__all__ = [
    "NAMESPACES",
    "ScoringInputError",
    "parse_typed_id",
    "canonical_id",
    "canonical_id_set",
    "canonicalize_finding",
    "canonicalize_truth",
    "validate_findings",
    "validate_truths",
]
