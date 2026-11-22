"""TP/FP/FN, F1 and the official reward — thin view over ``official_scorer``.

**Status: consolidated (BUG-TL-0001).** This module used to carry its own
reward implementation with the provisional formula
``R = max(0, F1 - ETA * steps_used / max_steps)``, ETA=0.05 (assumption
A-005). The organisers published the official definitions on 2026-11-20
(``spec/official_fintech_checks_2026-11-20.md``), which fix

  - ``return = clip([-1, 1], 2*F1 - 1 - 0.2 * inspection_steps / 100)``,
  - Block 3 test vectors such as ``0.98`` (test 1), ``47/150`` (tests 5,
    13), ``-871/1050`` (test 12) and ``-0.02`` (test 14),
  - ``P = R = 0`` for a clean book with an empty submission (test 3).

Keeping a second, divergent implementation meant that every internal
report (autohacker attribution, mutation suite, robustness audit, the
reward-property matrix) published numbers the jury would never reproduce:
the legacy formula failed 10 of 11 published test vectors.

There is now exactly one implementation of the reward —
:func:`scoring.official_scorer.compute_official_metrics`, which
``score_official_findings`` (and therefore ``judge_adapter.score_episode``)
already used. This module keeps the ``RewardBreakdown`` shape, the
config-loader and the exact-decimal helpers, and derives the reward from
that single source.

Arithmetic stays in ``fractions.Fraction``; decimal strings are rendered
only for display, rounded ROUND_HALF_EVEN to 7 places (TZ 15.5: the raw
reward is stored exactly). ``steps_used`` counts inspection tool calls
including erroneous ones, excluding submit (official border decision,
confirmed 2026-11-20 — no longer merely assumption A-06).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

from contracts.models import Finding, TruthFinding
from scoring.canon import ScoringInputError
from scoring.matcher import MatchResult, optimal_matching
from scoring.official_scorer import (
    OFFICIAL_STEP_PENALTY_WEIGHT,
    compute_official_metrics,
)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "scoring" / "default.json"
)

FORMULA = (
    "return = clip([-1, 1], 2*F1 - 1 - 0.2 * inspection_steps / 100)"
)

#: Display rounding for decimal renderings (raw values stay exact).
DISPLAY_PLACES = 7


@dataclass(frozen=True)
class ScoringConfig:
    """Validated reward parameters (from configs/scoring/default.json)."""

    eta: Fraction
    max_steps: int
    provisional: bool
    config_hash: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "eta_exact": str(self.eta),
            "eta_decimal": render_decimal(self.eta),
            "max_steps": self.max_steps,
            "provisional": self.provisional,
            "config_hash": self.config_hash,
            "source": self.source,
        }


@dataclass(frozen=True)
class RewardBreakdown:
    """Exact, transparent reward decomposition (TZ 15.9: reward breakdown)."""

    tp: int
    fp: int
    fn: int
    precision: Fraction
    recall: Fraction
    f1: Fraction
    eta: Fraction
    steps_used: int
    max_steps: int
    penalty: Fraction
    reward: Fraction
    formula: str
    provisional: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision_exact": str(self.precision),
            "precision_decimal": render_decimal(self.precision),
            "recall_exact": str(self.recall),
            "recall_decimal": render_decimal(self.recall),
            "f1_exact": str(self.f1),
            "f1_decimal": render_decimal(self.f1),
            "eta_exact": str(self.eta),
            "eta_decimal": render_decimal(self.eta),
            "steps_used": self.steps_used,
            "max_steps": self.max_steps,
            "penalty_exact": str(self.penalty),
            "penalty_decimal": render_decimal(self.penalty),
            "reward_exact": str(self.reward),
            "reward_decimal": render_decimal(self.reward),
            "formula": self.formula,
            "provisional": self.provisional,
        }


def render_decimal(value: Fraction, places: int = DISPLAY_PLACES) -> str:
    """Render an exact rational as a display string (ROUND_HALF_EVEN)."""
    with localcontext() as ctx:
        ctx.prec = 28
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
        quantum = Decimal(1).scaleb(-places)
        return format(decimal_value.quantize(quantum, rounding=ROUND_HALF_EVEN), "f")


def reward_metrics(
    tp: int, fp: int, fn: int, steps_used: int, *, step_budget: int
) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """The single reward path: ``(precision, recall, f1, clipped_return)``.

    ``compute_reward`` goes through this name so fault-injection suites can
    substitute the metric computation *on the real reward path* (the mutation
    suite patches this symbol). The arithmetic itself still lives only in
    :func:`scoring.official_scorer.compute_official_metrics`.
    """
    return compute_official_metrics(tp, fp, fn, steps_used, step_budget=step_budget)


def f1_score(tp: int, fp: int, fn: int) -> Fraction:
    """F1 from counts; clean book + empty submission yields 1 (official test 3)."""
    _validate_counts(tp, fp, fn)
    return compute_official_metrics(tp, fp, fn, 0)[2]


def precision_score(tp: int, fp: int) -> Fraction:
    """Precision from counts, with an empty submission defined as 1.

    NOTE — two different conventions coexist deliberately:

    * the **official reward** (``compute_official_metrics``) reports
      ``P = R = 0`` for a clean book with an empty submission (official
      Block 3 test 3), and that is what ``RewardBreakdown.precision``
      carries;
    * this helper keeps the **vacuous-truth** convention used by the
      generator cross-check (``scoring/crosscheck.py``), where "nothing was
      asserted and nothing was wrong" must read as perfect precision for a
      clean episode. Changing it to 0 would fail EXIT GATE 8 on clean
      episodes for a bookkeeping reason, not an accounting one.
    """
    _validate_counts(tp, fp, 0)
    if tp + fp == 0:
        return Fraction(1)
    return Fraction(tp, tp + fp)


def recall_score(tp: int, fn: int) -> Fraction:
    """Recall from counts, with an empty truth defined as 1.

    See :func:`precision_score` for why this is not the official
    ``P = R = 0`` reward convention.
    """
    _validate_counts(tp, 0, fn)
    if tp + fn == 0:
        return Fraction(1)
    return Fraction(tp, tp + fn)


def _validate_counts(tp: int, fp: int, fn: int) -> None:
    for name, value in (("tp", tp), ("fp", fp), ("fn", fn)):
        if type(value) is not int or value < 0:
            raise ScoringInputError(f"{name} must be a non-negative int")


def load_scoring_config(path: Path | str | None = None) -> ScoringConfig:
    """Load and validate reward parameters from a scoring config file.

    The config hash is recomputed with the canonical rules
    (REQ-CONTRACT-021); ``eta`` is parsed from its literal text
    (Decimal from string, never from binary float, REQ-MONEY-002
    analogue for reward arithmetic).
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    text = config_path.read_text(encoding="utf-8")
    try:
        exact = json.loads(text, parse_float=str)
        plain = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScoringInputError(f"scoring config is not valid JSON: {exc}") from exc
    if not isinstance(exact, dict):
        raise ScoringInputError("scoring config must be a JSON object")

    from contracts.canonical import config_hash

    stored_hash = exact.get("config_hash")
    if stored_hash is not None and stored_hash != config_hash(plain):
        raise ScoringInputError("scoring config_hash does not match its content")

    eta = _parse_eta(exact.get("eta"))
    max_steps = exact.get("max_steps")
    if type(max_steps) is not int or max_steps < 1:
        raise ScoringInputError("max_steps must be a positive int")
    provisional = exact.get("provisional", True)
    if not isinstance(provisional, bool):
        raise ScoringInputError("provisional must be a bool")
    return ScoringConfig(
        eta=eta,
        max_steps=max_steps,
        provisional=provisional,
        config_hash=stored_hash or config_hash(plain),
        source=str(config_path),
    )


def _parse_eta(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise ScoringInputError("eta must be numeric, not bool")
    if isinstance(value, int):
        eta = Fraction(value)
    elif isinstance(value, str):
        try:
            eta = Fraction(Decimal(value))
        except ArithmeticError as exc:
            raise ScoringInputError(f"eta literal is not exact decimal: {value!r}") from exc
    else:
        raise ScoringInputError(
            "eta must be an int or an exact decimal literal string"
        )
    if eta <= 0 or eta > 1:
        raise ScoringInputError("eta must lie in (0, 1]")
    return eta


def compute_reward(
    findings: Sequence[Finding],
    truths: Sequence[TruthFinding],
    steps_used: int,
    *,
    config: ScoringConfig | None = None,
    match_result: MatchResult | None = None,
) -> RewardBreakdown:
    """Compute the exact official reward for one episode outcome.

    Delegates the arithmetic to :func:`scoring.official_scorer.compute_official_metrics`
    so this module can never drift from the jury-facing scorer again
    (BUG-TL-0001). ``steps_used`` counts inspection tool calls (including
    erroneous ones, excluding submit — official border decision) and must
    satisfy ``0 <= steps_used <= max_steps``. The matcher is the single
    source of TP/FP/FN (REQ-SCORE-001).
    """
    scoring_config = config if config is not None else load_scoring_config()
    if type(steps_used) is not int or isinstance(steps_used, bool):
        raise ScoringInputError("steps_used must be an int")
    if not 0 <= steps_used <= scoring_config.max_steps:
        raise ScoringInputError(
            f"steps_used {steps_used} outside [0, {scoring_config.max_steps}]"
        )
    result = match_result if match_result is not None else optimal_matching(findings, truths)
    tp, fp, fn = result.tp, result.fp, result.fn
    precision, recall, f1, reward = reward_metrics(
        tp, fp, fn, steps_used, step_budget=scoring_config.max_steps
    )
    # The penalty reported in the breakdown is the one actually applied by the
    # official formula (weight 0.2), not the superseded provisional eta=0.05.
    # ``configs/scoring/default.json`` is a frozen contract and still carries
    # ``eta: 0.05``; that key no longer drives the reward (see D-18-01).
    penalty = OFFICIAL_STEP_PENALTY_WEIGHT * Fraction(steps_used, scoring_config.max_steps)
    return RewardBreakdown(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        # ``eta`` reports the weight actually applied by the official formula
        # so no consumer can read a stale 0.05 bound off the breakdown.
        eta=OFFICIAL_STEP_PENALTY_WEIGHT,
        steps_used=steps_used,
        max_steps=scoring_config.max_steps,
        penalty=penalty,
        reward=reward,
        formula=FORMULA,
        provisional=scoring_config.provisional,
    )


__all__ = [
    "OFFICIAL_STEP_PENALTY_WEIGHT",
    "ScoringConfig",
    "RewardBreakdown",
    "ScoringInputError",
    "FORMULA",
    "DISPLAY_PLACES",
    "render_decimal",
    "reward_metrics",
    "f1_score",
    "precision_score",
    "recall_score",
    "load_scoring_config",
    "compute_reward",
]
