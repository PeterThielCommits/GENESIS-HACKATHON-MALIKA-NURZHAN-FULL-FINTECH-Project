"""TP/FP/FN, F1 and the provisional official reward.

Implements Master TZ v3.0.0 sections 15.4-15.6 and Phase 6 task 6.5.

Definitions (explicit conventions, provisional until the organisers
publish the official rubric — Q-005, assumption A-005):

  - TP/FP/FN come from the matcher only (REQ-SCORE-001).
  - ``F1 = 2*TP / (2*TP + FP + FN)``; when TP = FP = FN = 0 (clean book,
    empty submission) ``F1 = 1`` by the explicit rule of TZ 15.4 —
    silence on a clean book is a correct audit.
  - ``precision = TP / (TP + FP)`` with an empty submission defined as
    ``precision = 1``; ``recall = TP / (TP + FN)`` with an empty truth
    defined as ``recall = 1``.
  - ``R = max(0, F1 - ETA * steps_used / max_steps)`` with ETA and
    max_steps read from ``configs/scoring/default.json`` (no hidden
    defaults, D-01-05). The formula stays provisional (A-005).

All arithmetic uses exact rationals (``fractions.Fraction``); decimal
strings are rendered only for display, rounded ROUND_HALF_EVEN to 7
places (TZ 15.5: raw reward is stored exactly). ``steps_used`` counts
inspection tool calls including erroneous ones, excluding submit
(assumption A-06, provisional).
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

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "configs" / "scoring" / "default.json"
)

FORMULA = "R = max(0, F1 - eta * steps_used / max_steps)"

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


def f1_score(tp: int, fp: int, fn: int) -> Fraction:
    """F1 from counts; clean book + empty submission yields 1 (TZ 15.4)."""
    _validate_counts(tp, fp, fn)
    if tp == 0 and fp == 0 and fn == 0:
        return Fraction(1)
    return Fraction(2 * tp, 2 * tp + fp + fn)


def precision_score(tp: int, fp: int) -> Fraction:
    """Precision from counts; empty submission is defined as 1."""
    _validate_counts(tp, fp, 0)
    if tp + fp == 0:
        return Fraction(1)
    return Fraction(tp, tp + fp)


def recall_score(tp: int, fn: int) -> Fraction:
    """Recall from counts; empty truth is defined as 1."""
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
    """Compute the exact reward for one episode outcome.

    ``steps_used`` counts inspection tool calls (including erroneous
    ones, excluding submit — provisional A-06) and must satisfy
    ``0 <= steps_used <= max_steps``. The matcher is the single source
    of TP/FP/FN (REQ-SCORE-001).
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
    f1 = f1_score(tp, fp, fn)
    penalty = scoring_config.eta * Fraction(steps_used, scoring_config.max_steps)
    reward = max(Fraction(0), f1 - penalty)
    return RewardBreakdown(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision_score(tp, fp),
        recall=recall_score(tp, fn),
        f1=f1,
        eta=scoring_config.eta,
        steps_used=steps_used,
        max_steps=scoring_config.max_steps,
        penalty=penalty,
        reward=reward,
        formula=FORMULA,
        provisional=scoring_config.provisional,
    )


__all__ = [
    "ScoringConfig",
    "RewardBreakdown",
    "ScoringInputError",
    "FORMULA",
    "DISPLAY_PLACES",
    "render_decimal",
    "f1_score",
    "precision_score",
    "recall_score",
    "load_scoring_config",
    "compute_reward",
]
