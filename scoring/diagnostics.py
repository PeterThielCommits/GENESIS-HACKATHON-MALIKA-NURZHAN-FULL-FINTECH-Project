"""Scoring diagnostics and the reward-property matrix.

Implements Master TZ v3.0.0 sections 15.7-15.9:

  - :func:`build_diagnostics` assembles everything the rubric asks for
    in diagnostics (counts, breakdowns, evidence coverage, flags,
    per-type results) WITHOUT feeding any of it back into the reward
    (TZ 15.9: no diagnostic metric influences reward);
  - :func:`build_reward_property_matrix` and
    :func:`evaluate_reward_properties` build the automatic results table
    of the five mandatory reward properties (TZ 15.7);
  - ``experimental_grounded_score`` (TZ 15.8) is computed only when the
    caller passes the evidence IDs actually requested before submit, is
    labelled experimental and lives in a separate column.

Items that belong to later phases (explanation consistency linter =
Phase 10, verifier quality = Phase 8) are reported as explicit
``NOT_AVAILABLE`` markers, never silently omitted (REQ-JUDGE-003
analogy). This module must not import gen/, verifier/, env/ or
harness/ (TZ 6).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Sequence

from contracts.models import Finding, TruthFinding
from scoring.canon import canonical_id_set, validate_findings, validate_truths
from scoring.matcher import MatchResult, optimal_matching
from scoring.official_scorer import official_formula_text
from scoring.reward import RewardBreakdown, render_decimal

DIAGNOSTICS_SCHEMA = "x_twinledger_internal_diagnostics/0.1.0"

NOT_AVAILABLE_EXPLANATION = {
    "status": "NOT_AVAILABLE",
    "reason": "explanation consistency linter is Phase 10 scope",
}
NOT_AVAILABLE_VERIFIER = {
    "status": "NOT_AVAILABLE",
    "reason": "verifier quality metrics are Phase 8 scope",
}
NOT_AVAILABLE_EVIDENCE_HIERARCHY = {
    "status": "NOT_AVAILABLE",
    "reason": "evidence hierarchy enforcement is Phase 10 scope",
}


def _exact(value: Fraction) -> dict[str, str]:
    return {"exact": str(value), "decimal": render_decimal(value)}


def build_diagnostics(
    findings: Sequence[Finding],
    truths: Sequence[TruthFinding],
    match_result: MatchResult,
    reward: RewardBreakdown,
    run_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the full diagnostics dict for one scored episode.

    ``run_info`` may carry ``steps_used`` (must agree with the reward),
    ``tool_calls``, ``truncated``, ``no_submit``, ``timeout``,
    ``difficulty``, ``policy_identifier`` and
    ``requested_evidence_ids`` (evidence IDs the policy actually
    queried before submit — enables the experimental grounded score of
    TZ 15.8).
    """
    info = dict(run_info or {})
    canon_findings = validate_findings(findings)
    canon_truths = validate_truths(truths)

    matches: list[dict[str, Any]] = []
    exact_amount_matches = 0
    minimal_evidence_matches = 0
    extra_evidence_total = 0
    for pair in match_result.pairs:
        finding = canon_findings[pair.finding_index]
        extra = tuple(sorted(set(finding.evidence_ids) - set(pair.evidence_set)))
        if pair.amount_error_minor == 0:
            exact_amount_matches += 1
        if len(pair.evidence_set) == canon_truths[pair.truth_index].minimal_evidence_size:
            minimal_evidence_matches += 1
        extra_evidence_total += len(extra)
        matches.append(
            {
                "finding_index": pair.finding_index,
                "truth_id": pair.truth_id,
                "type": canon_truths[pair.truth_index].type,
                "amount_error_minor": pair.amount_error_minor,
                "exact_amount": pair.amount_error_minor == 0,
                "evidence_set_index": pair.evidence_set_index,
                "evidence_set": list(pair.evidence_set),
                "extra_evidence_ids": list(extra),
            }
        )

    per_type = _per_type(canon_truths, match_result)
    optimal = _optimal_steps(canon_truths, match_result, reward.steps_used)
    flags = {
        "truncated": bool(info.get("truncated", False)),
        "no_submit": bool(info.get("no_submit", False)),
        "timeout": bool(info.get("timeout", False)),
        "clean_book": len(canon_truths) == 0,
    }
    audit_status = _audit_status(flags)

    diagnostics: dict[str, Any] = {
        "schema": DIAGNOSTICS_SCHEMA,
        "audit_status": audit_status,
        "counts": {
            "tp": match_result.tp,
            "fp": match_result.fp,
            "fn": match_result.fn,
            "findings_total": match_result.findings_total,
            "truths_total": match_result.truths_total,
        },
        "precision": _exact(reward.precision),
        "recall": _exact(reward.recall),
        "f1": _exact(reward.f1),
        "reward": reward.to_dict(),
        "matches": matches,
        "unmatched_findings": list(match_result.unmatched_findings),
        "unmatched_truths": [canon_truths[j].truth_id for j in match_result.unmatched_truths],
        "exact_match_counts": {
            "type": match_result.tp,
            "ids": match_result.tp,
            "amount": exact_amount_matches,
            "amount_within_tolerance": match_result.tp,
        },
        "steps_used": reward.steps_used,
        "tool_calls": info.get("tool_calls"),
        "flags": flags,
        "optimal_steps": optimal,
        "per_type": per_type,
        "evidence_coverage": {
            "matched_with_minimal_set": minimal_evidence_matches,
            "matched_with_superset": match_result.tp - minimal_evidence_matches,
            "extra_evidence_ids_total": extra_evidence_total,
        },
        "explanation_consistency": dict(
            info["explanation_consistency"]
            if isinstance(info.get("explanation_consistency"), dict)
            else NOT_AVAILABLE_EXPLANATION
        ),
        "evidence_hierarchy": dict(
            info["evidence_hierarchy"]
            if isinstance(info.get("evidence_hierarchy"), dict)
            else NOT_AVAILABLE_EVIDENCE_HIERARCHY
        ),
        "verifier_quality": dict(
            info["verifier_quality"]
            if isinstance(info.get("verifier_quality"), dict)
            else NOT_AVAILABLE_VERIFIER
        ),
    }
    if "difficulty" in info:
        diagnostics["difficulty"] = info["difficulty"]
    if "policy_identifier" in info:
        diagnostics["policy_identifier"] = info["policy_identifier"]
    diagnostics["experimental"] = _experimental(info, canon_findings, canon_truths, match_result)
    return diagnostics


def _audit_status(flags: dict[str, bool]) -> str:
    if flags["no_submit"] and flags["truncated"]:
        return "TRUNCATED_NO_SUBMIT"
    if flags["no_submit"]:
        return "NO_SUBMIT"
    if flags["truncated"]:
        return "TRUNCATED"
    if flags["timeout"]:
        return "TIMEOUT"
    return "OK"


def _per_type(
    truths: Sequence[TruthFinding], match_result: MatchResult
) -> dict[str, dict[str, Any]]:
    types = sorted({truth.type for truth in truths})
    out: dict[str, dict[str, Any]] = {}
    for anomaly_type in types:
        truth_indices = [j for j, t in enumerate(truths) if t.type == anomaly_type]
        tp = sum(1 for pair in match_result.pairs if pair.truth_index in truth_indices)
        fn = len(truth_indices) - tp
        out[anomaly_type] = {
            "tp": tp,
            "fn": fn,
            "truths": len(truth_indices),
            "recall": _exact(Fraction(tp, len(truth_indices)) if truth_indices else Fraction(1)),
        }
    return out


def _optimal_steps(
    truths: Sequence[TruthFinding], match_result: MatchResult, steps_used: int
) -> dict[str, Any]:
    model_ids = sorted({t.optimal_steps_model_id for t in truths if t.optimal_steps_model_id})
    declared = [t.optimal_steps for t in truths if t.optimal_steps is not None]
    if not declared:
        return {"status": "NOT_AVAILABLE", "reason": "truth declares no optimal_steps"}
    return {
        "model_ids": model_ids,
        "declared_optimal_steps_sum": sum(declared),
        "steps_used": steps_used,
    }


def _experimental(
    info: dict[str, Any],
    findings: Sequence[Finding],
    truths: Sequence[TruthFinding],
    match_result: MatchResult,
) -> dict[str, Any]:
    requested = info.get("requested_evidence_ids")
    if requested is None:
        return {
            "status": "NOT_RUN",
            "experimental_grounded_score": None,
            "note": (
                "experimental_grounded_score (TZ 15.8) requires "
                "requested_evidence_ids from the policy run; it never "
                "affects the official reward"
            ),
        }
    requested_set = set(canonical_id_set(requested))
    grounded_tp = 0
    for pair in match_result.pairs:
        if set(pair.evidence_set).issubset(requested_set):
            grounded_tp += 1
    grounded_fp = match_result.findings_total - grounded_tp
    grounded_fn = match_result.truths_total - grounded_tp
    if grounded_tp == 0 and grounded_fp == 0 and grounded_fn == 0:
        grounded_f1 = Fraction(1)
    else:
        grounded_f1 = Fraction(
            2 * grounded_tp, 2 * grounded_tp + grounded_fp + grounded_fn
        )
    return {
        "status": "EXPERIMENTAL",
        "experimental_grounded_score": _exact(grounded_f1),
        "grounded_tp": grounded_tp,
        "grounded_fp": grounded_fp,
        "grounded_fn": grounded_fn,
        "note": "research indicator only (TZ 15.8); never part of the official reward",
    }


def build_reward_property_matrix(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Build the automatic reward test matrix (TZ 15.7).

    Each row describes one (scenario, strategy) scoring outcome:
    ``scenario``, ``strategy``, ``kind`` (``dirty``/``clean``),
    ``anomaly_type``, ``tp``/``fp``/``fn``, ``steps_used``,
    ``reward_exact``/``reward_decimal``. The summary computes exact
    mean rewards per strategy; row order is preserved.
    """
    summary_rows: dict[str, list[Fraction]] = {}
    materialised: list[dict[str, Any]] = []
    for row in rows:
        reward = Fraction(row["reward_exact"])
        summary_rows.setdefault(row["strategy"], []).append(reward)
        materialised.append(dict(row))
    summary = {}
    for strategy in sorted(summary_rows):
        values = summary_rows[strategy]
        mean = sum(values, Fraction(0)) / len(values)
        summary[strategy] = {
            "n": len(values),
            "mean_reward_exact": str(mean),
            "mean_reward_decimal": render_decimal(mean),
        }
    return {
        "generated_by": "scoring.diagnostics.build_reward_property_matrix",
        # BUG-TL-0005: the matrix numbers come from the single official
        # implementation (``scoring.official_scorer``), so the matrix is NOT
        # provisional, and the formula it publishes is the live formula --
        # derived from the live constants, not a second literal. The old
        # values ("provisional": true and the superseded provisional formula
        # "R = max(0, F1 - eta * steps_used / max_steps)") described a reward
        # implementation that no longer exists (D-18-01).
        "provisional": False,
        "formula": official_formula_text(),
        "rows": materialised,
        "summary": summary,
    }


def evaluate_reward_properties(matrix: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the five mandatory reward properties over a matrix.

    P1 dirty book: a correct answer beats silence;
    P2 clean book: silence beats false accusations;
    P3 duplicates/splits give no advantage over the honest answer;
    P4 flag-all is worse than the honest strategy on the corpus;
    P5 step savings distinguish equal completeness only boundedly:
       rewards are non-increasing in steps_used and the maximal total
       step penalty never exceeds the official weight (0.2).

    Returns per-property ``pass`` flags with per-check details; the
    caller decides how to surface them (test assertions + artifact).
    """
    rows = matrix["rows"]
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault((row["scenario"], row["strategy"]), []).append(row)

    def reward_of(scenario: str, strategy: str) -> Fraction:
        return Fraction(by_key[(scenario, strategy)][0]["reward_exact"])

    checks: dict[str, list[dict[str, Any]]] = {"P1": [], "P2": [], "P3": [], "P4": [], "P5": []}

    scenarios = sorted({row["scenario"] for row in rows})
    for scenario in scenarios:
        kind = next(row["kind"] for row in rows if row["scenario"] == scenario)
        if kind == "dirty" and (scenario, "honest") in by_key and (
            scenario,
            "silence",
        ) in by_key:
            honest = reward_of(scenario, "honest")
            silence = reward_of(scenario, "silence")
            checks["P1"].append(
                {
                    "scenario": scenario,
                    "honest": str(honest),
                    "silence": str(silence),
                    "pass": honest > silence,
                }
            )
        if kind == "clean" and (scenario, "silence") in by_key and (
            scenario,
            "false_accusation",
        ) in by_key:
            silence = reward_of(scenario, "silence")
            accusation = reward_of(scenario, "false_accusation")
            checks["P2"].append(
                {
                    "scenario": scenario,
                    "silence": str(silence),
                    "false_accusation": str(accusation),
                    "pass": silence > accusation,
                }
            )
        if kind == "dirty" and (scenario, "honest") in by_key:
            honest = reward_of(scenario, "honest")
            for strategy in ("duplicate_spam", "split"):
                if (scenario, strategy) in by_key:
                    other = reward_of(scenario, strategy)
                    checks["P3"].append(
                        {
                            "scenario": scenario,
                            "strategy": strategy,
                            "honest": str(honest),
                            "attack": str(other),
                            "pass": other <= honest,
                        }
                    )

    strategies = matrix["summary"]
    if "flag_all" in strategies and "honest" in strategies:
        flag_mean = Fraction(strategies["flag_all"]["mean_reward_exact"])
        honest_mean = Fraction(strategies["honest"]["mean_reward_exact"])
        checks["P4"].append(
            {
                "flag_all_mean": str(flag_mean),
                "honest_mean": str(honest_mean),
                "pass": flag_mean < honest_mean,
            }
        )

    eta_values = [Fraction(row["eta_exact"]) for row in rows if "eta_exact" in row]
    eta_bound = max(eta_values) if eta_values else None
    for (scenario, strategy), group in sorted(by_key.items()):
        ordered = sorted(group, key=lambda row: row["steps_used"])
        steps = [row["steps_used"] for row in ordered]
        rewards = [Fraction(row["reward_exact"]) for row in ordered]
        if len(set(steps)) < 2:
            continue
        monotone = all(a >= b for a, b in zip(rewards, rewards[1:]))
        spread = rewards[0] - rewards[-1]
        bounded = eta_bound is None or spread <= eta_bound
        checks["P5"].append(
            {
                "scenario": scenario,
                "strategy": strategy,
                "steps": steps,
                "rewards": [str(value) for value in rewards],
                "non_increasing": monotone,
                "max_spread": str(spread),
                # ``eta_bound`` is the historical key name; the value is the
                # official step-penalty weight actually applied by the reward
                # (0.2), not the superseded provisional 0.05 (BUG-TL-0001/0005).
                "eta_bound": str(eta_bound) if eta_bound is not None else None,
                "step_penalty_bound_exact": str(eta_bound) if eta_bound is not None else None,
                "pass": monotone and bounded,
            }
        )

    return {
        property_id: {
            "pass": all(item["pass"] for item in items) if items else False,
            "checks": items,
        }
        for property_id, items in checks.items()
    }


__all__ = [
    "DIAGNOSTICS_SCHEMA",
    "build_diagnostics",
    "build_reward_property_matrix",
    "evaluate_reward_properties",
]
