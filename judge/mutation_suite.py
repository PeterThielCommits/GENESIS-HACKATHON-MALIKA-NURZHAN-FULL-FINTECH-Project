#!/usr/bin/env python3
"""26-Mutant Matcher, Reward & Lifecycle Mutation Testing Suite (Phase 13 — TZ §20.5).

Applies 26 targeted artificial defects (``MUT-01 .. MUT-26``, covering every
mandatory mutant class in Master TZ §20.5) via controlled ``unittest.mock.patch``
contexts on the production ``scoring/`` and ``env/`` modules, then executes the
verification test battery against each mutant.

Target: 26 / 26 mutants killed (100% mutation score), 0 surviving mutants, and
100% pass on the unmutated control run.

Writes ``artifacts/reports/latest/mutation_test_report.json``.
"""

from __future__ import annotations

import json
import platform
import random
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import env.environment as env_mod
import scoring.canon as canon_mod
import scoring.diagnostics as diag_mod
import scoring.matcher as matcher_mod
import scoring.reward as reward_mod
from contracts.canonical import canonical_json, sha256_hex
from contracts.models import Finding, TruthFinding
from contracts.version import PROTOCOL_VERSION

DEFAULT_REPORT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "mutation_test_report.json"


def _sample_truth(
    truth_id: str = "T-001",
    *,
    atype: str = "DUPLICATE_PAYMENT",
    affected: tuple[str, ...] = ("INV:101", "PAY:201"),
    amount: int = 10000,
    currency: str = "KZT",
    tolerance: int = 10,
    ev_sets: tuple[tuple[str, ...], ...] = (("INV:101", "PAY:201"),),
) -> TruthFinding:
    return TruthFinding.from_dict(
        {
            "schema_version": "1.0.0",
            "truth_id": truth_id,
            "type": atype,
            "affected_ids": list(affected),
            "amount_minor": amount,
            "currency": currency,
            "tolerance_minor": tolerance,
            "evidence_sets": [list(s) for s in ev_sets],
            "evidence_enumeration_complete": True,
            "minimal_evidence_size": min(len(s) for s in ev_sets),
            "invariant_signature": {"invariant_id": "INV-04"},
            "operator_version": "gen-operators@1.0.0",
        }
    )


def _sample_finding(
    *,
    atype: str = "DUPLICATE_PAYMENT",
    affected: tuple[str, ...] = ("INV:101", "PAY:201"),
    amount: int = 10000,
    currency: str = "KZT",
    evidence: tuple[str, ...] = ("INV:101", "PAY:201"),
    explanation: str = "Short.",
) -> Finding:
    return Finding.from_dict(
        {
            "schema_version": "1.0.0",
            "type": atype,
            "affected_ids": list(affected),
            "claimed_amount": amount,
            "currency": currency,
            "evidence_ids": list(evidence),
            "explanation": explanation,
        }
    )


def _verification_battery() -> None:
    """Comprehensive fast assertion battery covering all TZ §15 & §20.5 invariants."""
    t1 = _sample_truth("T-001", amount=10000, tolerance=10)
    t2 = _sample_truth(
        "T-002",
        atype="FX_RATE_MISMATCH",
        affected=("JE:301",),
        amount=5000,
        currency="JPY",
        tolerance=0,
        ev_sets=(("FX:401", "INV:102", "JE:301"),),
    )

    # 1. Exact match & boundary tolerance
    f_exact = _sample_finding(amount=10000)
    f_bound = _sample_finding(amount=10010)
    f_over = _sample_finding(amount=10050)
    assert matcher_mod.optimal_matching([f_exact], [t1]).tp == 1
    assert matcher_mod.optimal_matching([f_bound], [t1]).tp == 1
    assert matcher_mod.optimal_matching([f_over], [t1]).tp == 0

    # 2. Type, currency, affected_ids, and evidence checks
    assert matcher_mod.optimal_matching([_sample_finding(atype="PERIOD_CUTOFF")], [t1]).tp == 0
    assert matcher_mod.optimal_matching([_sample_finding(currency="USD")], [t1]).tp == 0
    assert matcher_mod.optimal_matching([_sample_finding(affected=("INV:101",))], [t1]).tp == 0
    assert matcher_mod.optimal_matching([_sample_finding(evidence=("INV:101",))], [t1]).tp == 0

    # 3. Multi-element minimal evidence set (catches truncation before check)
    f_fx = _sample_finding(
        atype="FX_RATE_MISMATCH",
        affected=("JE:301",),
        amount=5000,
        currency="JPY",
        evidence=("FX:401", "INV:102", "JE:301"),
    )
    assert matcher_mod.optimal_matching([f_fx], [t2]).tp == 1

    # 4. Duplicate & split findings never inflate TP; FP and FN both affect F1
    mr_dup = matcher_mod.optimal_matching([f_exact, f_exact], [t1])
    assert mr_dup.tp == 1 and mr_dup.fp == 1
    rb_dup = reward_mod.compute_reward([f_exact, f_exact], [t1], 10)
    rb_single = reward_mod.compute_reward([f_exact], [t1], 10)
    assert rb_dup.reward < rb_single.reward

    # One finding cannot match two distinct truths simultaneously
    t1_clone = _sample_truth("T-001B", amount=10000, tolerance=10)
    mr_one_to_two = matcher_mod.optimal_matching([f_exact], [t1, t1_clone])
    assert mr_one_to_two.tp == 1 and mr_one_to_two.fn == 1
    rb_fn = reward_mod.compute_reward([f_exact], [t1, t1_clone], 0)
    assert rb_fn.f1 == Fraction(2, 3)

    # Split finding rejected
    f_half1 = _sample_finding(amount=5000)
    f_half2 = _sample_finding(amount=5000)
    assert reward_mod.compute_reward([f_half1, f_half2], [t1], 0).tp == 0

    # 5. Clean silence == F1=1, step penalty monotonically decreases reward, exact Fraction math
    rb_clean_0 = reward_mod.compute_reward([], [], 0)
    rb_clean_20 = reward_mod.compute_reward([], [], 20)
    assert rb_clean_0.f1 == Fraction(1)
    assert rb_clean_20.reward < rb_clean_0.reward
    assert rb_clean_20.reward == Fraction(1) - reward_mod.load_scoring_config().eta * Fraction(20, 100)

    # Exact rational precision check (catches binary float drift on 2/3 - 0.05 * 30 / 100)
    rb_third = reward_mod.compute_reward([f_exact], [t1, t1_clone], 30)
    expected_exact = Fraction(2, 3) - reward_mod.load_scoring_config().eta * Fraction(30, 100)
    assert rb_third.reward == expected_exact

    # 6. Explanation invariance
    f_eloquent = _sample_finding(explanation="Detailed audit narrative " * 8)
    assert reward_mod.compute_reward([f_exact], [t1], 5).reward == reward_mod.compute_reward([f_eloquent], [t1], 5).reward

    # 7. Optimal bipartite matching beats naive greedy input-order matching + deterministic tie-break
    # Left 0 can match Right 0 or Right 1; Left 1 can ONLY match Right 0 -> max cardinality is 2!
    cost_augment = [[0, 0], [0, None]]
    pairs_aug = matcher_mod.optimal_pairs(cost_augment)
    assert len(pairs_aug) == 2

    # Tie-break determinism across 10 repeats
    cost_tie = [[0, 0], [None, None]]
    first_tb = matcher_mod.optimal_pairs(cost_tie)
    assert first_tb == [(0, 0)]
    for _ in range(8):
        assert matcher_mod.optimal_pairs(cost_tie) == [(0, 0)]

    # 8. Diagnostics truncated flag
    diag_trunc = diag_mod.build_diagnostics(
        [],
        [],
        matcher_mod.optimal_matching([], []),
        rb_clean_0,
        run_info={"truncated": True, "no_submit": True},
    )
    assert diag_trunc["audit_status"] != "OK"

    # 9. Bounds & schema validation checks (unknown type, empty affected_ids, steps > max_steps)
    try:
        reward_mod.compute_reward([], [], 999)
        raise AssertionError("expected ScoringInputError for steps_used > max_steps")
    except canon_mod.ScoringInputError:
        pass

    try:
        canon_mod.validate_findings(
            [
                Finding(
                    type="INVENTED_UNKNOWN_TYPE",
                    affected_ids=("INV:101",),
                    claimed_amount=100,
                    currency="KZT",
                    evidence_ids=("INV:101",),
                )
            ]
        )
        raise AssertionError("expected ScoringInputError for unknown type")
    except (canon_mod.ScoringInputError, ValueError):
        pass

    try:
        canon_mod.validate_findings(
            [
                Finding(
                    type="DUPLICATE_PAYMENT",
                    affected_ids=(),
                    claimed_amount=100,
                    currency="KZT",
                    evidence_ids=("INV:101",),
                )
            ]
        )
        raise AssertionError("expected ScoringInputError for empty affected_ids")
    except (canon_mod.ScoringInputError, ValueError):
        pass

    # 10. Environment submit lifecycle: submit does NOT increment steps_used & second submit rejected
    ep_dev = REPO_ROOT / "episodes" / "dev"
    first_ep = next(p for p in sorted(ep_dev.iterdir()) if (p / "public").is_dir())
    env = env_mod.TwinLedgerEnv(env_mod.EnvConfig(mode="CLOSED_EVAL", submit_counts_as_step=False))
    env.reset(first_ep / "public", cursor_seed=1)
    r_sub1 = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "s1", "action": {"tool": "submit", "args": {"findings": []}}})
    assert r_sub1["ok"] is True
    assert env.steps_used == 0
    r_sub2 = env.step(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "s2",
            "action": {
                "tool": "submit",
                "args": {
                    "findings": [
                        {
                            "schema_version": "1.0.0",
                            "type": "DUPLICATE_PAYMENT",
                            "affected_ids": ["INV:101"],
                            "claimed_amount": 100,
                            "currency": "KZT",
                            "evidence_ids": ["INV:101"],
                        }
                    ]
                },
            },
        }
    )
    assert r_sub2["ok"] is False
    assert env.submitted_findings == []


@dataclass(frozen=True)
class MutantSpec:
    mutant_id: str
    name: str
    tz_class: str
    patch_ctx: Callable[[], Iterator[None]]


def _build_mutants() -> tuple[MutantSpec, ...]:
    orig_pred = matcher_mod._predicate_canonical
    orig_opt_pairs = matcher_mod.optimal_pairs
    orig_opt_match = matcher_mod.optimal_matching
    orig_comp_rew = reward_mod.compute_reward
    orig_f1 = reward_mod.f1_score
    orig_audit = diag_mod._audit_status
    orig_val_f = canon_mod.validate_findings
    orig_step = env_mod.TwinLedgerEnv.step

    @contextmanager
    def m01():
        def bad(f: Finding, t: TruthFinding):
            return orig_pred(Finding(**{**f.__dict__, "type": t.type}), t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m02():
        def bad(f: Finding, t: TruthFinding):
            return orig_pred(Finding(**{**f.__dict__, "currency": t.currency}), t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m03():
        def bad(f: Finding, t: TruthFinding):
            if set(f.affected_ids) & set(t.affected_ids):
                f = Finding(**{**f.__dict__, "affected_ids": t.affected_ids})
            return orig_pred(f, t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m04():
        def bad(f: Finding, t: TruthFinding):
            return orig_pred(Finding(**{**f.__dict__, "evidence_ids": t.evidence_sets[0]}), t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m05():
        def bad(f: Finding, t: TruthFinding):
            t_wide = TruthFinding(**{**t.__dict__, "tolerance_minor": t.tolerance_minor + 100000})
            return orig_pred(f, t_wide)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m06():
        def bad(findings, truths, steps_used, **kw):
            rb = orig_comp_rew(findings, truths, steps_used, **kw)
            plus = rb.f1 + rb.eta * Fraction(steps_used, rb.max_steps)
            return reward_mod.RewardBreakdown(**{**rb.__dict__, "reward": plus})
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m07():
        with patch.object(reward_mod, "f1_score", lambda tp, fp, fn: orig_f1(tp, 0, fn)):
            yield

    @contextmanager
    def m08():
        with patch.object(reward_mod, "f1_score", lambda tp, fp, fn: orig_f1(tp, fp, 0)):
            yield

    @contextmanager
    def m09():
        def bad(findings, truths):
            res = orig_opt_match(findings, truths)
            if len(findings) >= 2 and len(truths) == 1:
                return matcher_mod.MatchResult(**{**res.__dict__, "tp": len(findings), "fp": 0})
            return res
        with patch.object(matcher_mod, "optimal_matching", bad):
            yield

    @contextmanager
    def m10():
        def bad(findings, truths):
            res = orig_opt_match(findings, truths)
            if len(findings) == 1 and len(truths) >= 2 and res.tp == 1:
                return matcher_mod.MatchResult(**{**res.__dict__, "tp": len(truths), "fn": 0})
            return res
        with patch.object(matcher_mod, "optimal_matching", bad):
            yield

    @contextmanager
    def m11():
        def bad(findings, truths, steps_used, **kw):
            rb = orig_comp_rew(findings, truths, steps_used, **kw)
            if len(findings) > 1:
                return reward_mod.RewardBreakdown(**{**rb.__dict__, "reward": Fraction(1)})
            return rb
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m12():
        with patch.object(diag_mod, "_audit_status", lambda flags: "OK"):
            yield

    @contextmanager
    def m13():
        def bad(tp: int, fp: int, fn: int) -> Fraction:
            if tp == 0 and fp == 0 and fn == 0:
                return Fraction(0)
            return orig_f1(tp, fp, fn)
        with patch.object(reward_mod, "f1_score", bad):
            yield

    @contextmanager
    def m14():
        def bad(findings, truths, steps_used, **kw):
            rb = orig_comp_rew(findings, truths, steps_used, **kw)
            if any(len(f.explanation or "") > 40 for f in findings):
                return reward_mod.RewardBreakdown(**{**rb.__dict__, "reward": rb.reward + Fraction(1, 20)})
            return rb
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m15():
        def bad(findings, truths, steps_used, **kw):
            rb = orig_comp_rew(findings, truths, steps_used, **kw)
            f_val = round(float(rb.f1) - float(rb.eta) * (steps_used / rb.max_steps), 4)
            return reward_mod.RewardBreakdown(**{**rb.__dict__, "reward": Fraction(str(f_val))})
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m16():
        def greedy(cost: list[list[int | None]]) -> list[tuple[int, int]]:
            used_r: set[int] = set()
            out: list[tuple[int, int]] = []
            for i, row in enumerate(cost):
                for j in reversed(range(len(row))):
                    if row[j] is not None and j not in used_r:
                        used_r.add(j)
                        out.append((i, j))
                        break
            return out
        with patch.object(matcher_mod, "optimal_pairs", greedy):
            yield

    @contextmanager
    def m17():
        def bad(f: Finding, t: TruthFinding):
            scaled = Finding(**{**f.__dict__, "claimed_amount": f.claimed_amount * (100 if f.currency == "JPY" else 1)})
            return orig_pred(scaled, t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m18():
        def bad(f: Finding, t: TruthFinding):
            return orig_pred(Finding(**{**f.__dict__, "evidence_ids": f.evidence_ids[:1]}), t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    @contextmanager
    def m19():
        def bad(findings: Sequence[Finding], truths: Sequence[TruthFinding], steps_used: int, **kw):
            if len(findings) >= 2 and len(truths) == 1:
                merged = Finding(**{**findings[0].__dict__, "claimed_amount": sum(x.claimed_amount for x in findings)})
                return orig_comp_rew([merged], truths, steps_used, **kw)
            return orig_comp_rew(findings, truths, steps_used, **kw)
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m20():
        with patch.object(canon_mod, "validate_findings", lambda fs: list(fs)):
            yield

    @contextmanager
    def m21():
        rng = random.Random(99)
        def rand_tb(cost: list[list[int | None]]) -> list[tuple[int, int]]:
            if len(cost) >= 1 and len(cost[0]) >= 2 and cost[0][0] == 0 and cost[0][1] == 0:
                return [(0, rng.choice([0, 1]))]
            return orig_opt_pairs(cost)
        with patch.object(matcher_mod, "optimal_pairs", rand_tb):
            yield

    @contextmanager
    def m22():
        def bad_step(self, request):
            if isinstance(request, dict) and (request.get("action") or {}).get("tool") == "submit" and self._submitted:
                self._submitted_findings = list((request["action"].get("args") or {}).get("findings") or [])
                return self._ok_response(str(request.get("request_id", "s")), {"submitted": True})
            return orig_step(self, request)
        with patch.object(env_mod.TwinLedgerEnv, "step", bad_step):
            yield

    @contextmanager
    def m23():
        def bad_step(self, request):
            res = orig_step(self, request)
            if isinstance(request, dict) and (request.get("action") or {}).get("tool") == "submit" and res.get("ok"):
                self._steps_used += 1
            return res
        with patch.object(env_mod.TwinLedgerEnv, "step", bad_step):
            yield

    @contextmanager
    def m24():
        def bad(findings, truths, steps_used, **kw):
            capped = min(int(steps_used), 100)
            return orig_comp_rew(findings, truths, capped, **kw)
        with patch.object(reward_mod, "compute_reward", bad):
            yield

    @contextmanager
    def m25():
        def bad(fs):
            patched = [Finding(**{**f.__dict__, "affected_ids": ("INV:DUMMY",)}) if not f.affected_ids else f for f in fs]
            return orig_val_f(patched)
        with patch.object(canon_mod, "validate_findings", bad):
            yield

    @contextmanager
    def m26():
        def bad(f: Finding, t: TruthFinding):
            if abs(f.claimed_amount - t.amount_minor) == t.tolerance_minor and t.tolerance_minor > 0:
                return matcher_mod.MatchDecision(False, matcher_mod.REASON_AMOUNT, t.tolerance_minor)
            return orig_pred(f, t)
        with patch.object(matcher_mod, "_predicate_canonical", bad):
            yield

    return (
        MutantSpec("MUT-01", "ignore_type", "ignore_type", m01),
        MutantSpec("MUT-02", "ignore_currency", "ignore_currency", m02),
        MutantSpec("MUT-03", "weaken_affected_ids_subset", "weaken_affected_ids", m03),
        MutantSpec("MUT-04", "skip_evidence_check", "skip_evidence", m04),
        MutantSpec("MUT-05", "excessive_tolerance", "wide_tolerance", m05),
        MutantSpec("MUT-06", "flip_step_penalty_sign", "step_penalty_sign", m06),
        MutantSpec("MUT-07", "forget_false_positives", "forget_fp", m07),
        MutantSpec("MUT-08", "forget_false_negatives", "forget_fn", m08),
        MutantSpec("MUT-09", "match_truth_multiple_times", "multi_match_truth", m09),
        MutantSpec("MUT-10", "match_finding_multiple_times", "multi_match_finding", m10),
        MutantSpec("MUT-11", "reward_duplicate_predictions", "duplicate_advantage", m11),
        MutantSpec("MUT-12", "ignore_truncated_flag", "ignore_truncated", m12),
        MutantSpec("MUT-13", "penalize_clean_silence", "clean_silence_error", m13),
        MutantSpec("MUT-14", "explanation_length_bonus", "explanation_reward_leak", m14),
        MutantSpec("MUT-15", "float_precision_drift", "float_rounding_bug", m15),
        MutantSpec("MUT-16", "input_order_dependent_greedy", "input_order_dependence", m16),
        MutantSpec("MUT-17", "ignore_currency_exponent", "skip_currency_exponent", m17),
        MutantSpec("MUT-18", "truncate_evidence_before_check", "truncate_evidence_list", m18),
        MutantSpec("MUT-19", "accept_split_findings", "accept_split_finding", m19),
        MutantSpec("MUT-20", "accept_unknown_finding_type", "skip_unknown_type_validation", m20),
        MutantSpec("MUT-21", "random_seed_tie_break", "seeded_tie_break", m21),
        MutantSpec("MUT-22", "allow_second_submit_override", "second_submit_mutation", m22),
        MutantSpec("MUT-23", "count_submit_as_inspection_step", "submit_counted_as_step", m23),
        MutantSpec("MUT-24", "skip_max_steps_bounds_check", "skip_max_steps_cap", m24),
        MutantSpec("MUT-25", "drop_required_affected_ids_check", "missing_required_anomaly_field", m25),
        MutantSpec("MUT-26", "strict_less_than_tolerance_off_by_one", "tolerance_boundary_off_by_one", m26),
    )


def run_mutation_suite(*, output_path: Path | str | None = None) -> dict[str, Any]:
    out_file = Path(output_path) if output_path else DEFAULT_REPORT_PATH

    # Control run on unmutated production code must pass 100%
    _verification_battery()

    mutants = _build_mutants()
    records: list[dict[str, Any]] = []
    killed_count = 0

    for m in mutants:
        killed = False
        kill_reason = ""
        try:
            with m.patch_ctx():
                _verification_battery()
        except Exception as exc:
            killed = True
            kill_reason = f"{type(exc).__name__}: {exc}"[:160]
        if killed:
            killed_count += 1
        records.append(
            {
                "mutant_id": m.mutant_id,
                "name": m.name,
                "tz_class": m.tz_class,
                "killed": killed,
                "kill_signal": kill_reason or "SURVIVED",
            }
        )

    total = len(mutants)
    surviving = total - killed_count
    passed = total >= 25 and surviving == 0

    cfg_meta = {"mutant_ids": [m.mutant_id for m in mutants]}
    report = {
        "schema_version": "1.0.0",
        "report_type": "mutation_test_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(cfg_meta),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 judge/mutation_suite.py",
        "status": "PASS" if passed else "FAIL",
        "summary": {
            "total_mutants": total,
            "killed_mutants": killed_count,
            "surviving_mutants": surviving,
            "mutation_score_exact": f"{killed_count}/{total}",
            "mutation_score_pct": round((100.0 * killed_count) / max(1, total), 2),
        },
        "mutants": records,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    rep = run_mutation_suite()
    s = rep["summary"]
    print(
        f"[{rep['status']}] mutation suite: {s['killed_mutants']}/{s['total_mutants']} "
        f"killed ({s['mutation_score_pct']}%) -> {DEFAULT_REPORT_PATH}"
    )
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
