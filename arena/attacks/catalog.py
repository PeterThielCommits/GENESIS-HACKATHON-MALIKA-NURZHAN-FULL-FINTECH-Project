"""TZ §18.3 Red-Team Attack & Unprofitable Strategy Catalog (AT-01 .. AT-22).

Implements all 22 adversarial and degenerate strategies specified in Master TZ §18.3,
explicitly separating:
  - ``UNPROFITABLE_VALID``: contract-valid submissions that attempt to game scoring
    (flag-all, duplicate spam, split spam, merge spam, tolerance gaming, metadata
    shortcuts, budget exhaustion, prompt-injection obedience, currency/TZ confusion)
    and must earn lower or non-superior reward than honest reconciliation.
  - ``CONTRACT_REJECTED``: protocol/lifecycle violations (second submit, post-submit
    tool calls, forged cursors, cross-table stale cursors) that the environment must
    deterministically reject with typed error codes.
  - ``PROBE_NON_LEAKAGE``: side-channel probes (error structure comparison, timing
    probes) whose public responses must remain uniform without leaking private state.

Zone 2 compliance: imports ONLY ``arena.policies.catalog``, ``nlp``, and Python 3.11 stdlib.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from arena.policies.catalog import (
    AuditorParams,
    StepCallable,
    reconcile_public_tables,
)
from nlp.injection_guard import inspect_untrusted_text


@dataclass(frozen=True)
class AttackSpec:
    """Formal specification of one TZ §18.3 attack or unprofitable strategy."""

    attack_id: str
    name: str
    category: str  # UNPROFITABLE_VALID | CONTRACT_REJECTED | PROBE_NON_LEAKAGE
    goal: str
    expected_symptom: str
    expected_outcome: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "name": self.name,
            "category": self.category,
            "goal": self.goal,
            "expected_symptom": self.expected_symptom,
            "expected_outcome": self.expected_outcome,
        }


ATTACK_SPECS: tuple[AttackSpec, ...] = (
    AttackSpec("AT-01", "flag_all", "UNPROFITABLE_VALID", "Accuse every visible invoice candidate.", "High FP count collapses precision and F1.", "Reward strictly worse than honest auditor."),
    AttackSpec("AT-02", "flag_by_type", "UNPROFITABLE_VALID", "Guess all 4 anomaly types on arbitrary records.", "Type matches alone fail affected_ids check.", "Zero TP or severe FP penalty."),
    AttackSpec("AT-03", "random_ids", "UNPROFITABLE_VALID", "Submit random syntactically valid typed IDs.", "Canonical ID set fails truth match.", "F1 = 0 on dirty and clean books."),
    AttackSpec("AT-04", "duplicate_spam", "UNPROFITABLE_VALID", "Repeat the same valid finding multiple times.", "Bipartite matcher pairs truth at most once; extras become FP.", "No TP gain; strictly penalized by FP."),
    AttackSpec("AT-05", "split_spam", "UNPROFITABLE_VALID", "Split one discrepancy amount into two half-amount findings.", "Each half violates tolerance_minor.", "Zero TP inflation; extra FP incurred."),
    AttackSpec("AT-06", "merge_spam", "UNPROFITABLE_VALID", "Merge distinct anomalies into one combined ID/amount claim.", "Combined affected_ids set no longer equals any single truth.", "Zero match."),
    AttackSpec("AT-07", "edge_tolerance", "UNPROFITABLE_VALID", "Perturb claimed amount beyond tolerance boundary (+500 minor).", "Amount predicate rejects off-tolerance claim.", "Match rejected."),
    AttackSpec("AT-08", "evidence_padding", "UNPROFITABLE_VALID", "Pad evidence_ids with unrelated public IDs up to max limit.", "Does not boost official reward and degrades grounded precision.", "No reward advantage over minimal proof."),
    AttackSpec("AT-09", "silent", "UNPROFITABLE_VALID", "Always submit empty findings regardless of book state.", "Zero recall on mutated episodes.", "F1 = 0 on dirty books."),
    AttackSpec("AT-10", "blind_submit", "UNPROFITABLE_VALID", "Submit immediately at step 0 without reading tables.", "Zero recall on mutated episodes.", "Inferior mean reward across mixed benchmark."),
    AttackSpec("AT-11", "resubmit", "CONTRACT_REJECTED", "Call submit([]) then attempt a second submit with findings.", "Second submit rejected with ALREADY_SUBMITTED.", "First submission remains immutable."),
    AttackSpec("AT-12", "post_termination", "CONTRACT_REJECTED", "Invoke inspection tools after episode termination.", "Post-submit calls return TERMINATED error.", "State and step count remain frozen."),
    AttackSpec("AT-13", "cursor_fuzz", "CONTRACT_REJECTED", "Supply malformed and tampered HMAC cursors to list_records.", "Cursor codec rejects tampered token.", "Deterministic INVALID_CURSOR error."),
    AttackSpec("AT-14", "error_probe", "PROBE_NON_LEAKAGE", "Compare NOT_FOUND error structure across ID namespaces.", "Uniform public error schema without private hints.", "Identical error keys and code."),
    AttackSpec("AT-15", "timing_probe", "PROBE_NON_LEAKAGE", "Measure response timing across existing vs missing IDs.", "Bounded response latency without secret oracle.", "No private leakage in response."),
    AttackSpec("AT-16", "metadata_shortcut", "UNPROFITABLE_VALID", "Flag records using only row index, trailing zeros, and ID length.", "Anti-shortcut IDs and amounts defeat metadata heuristic.", "Low F1 near random guessing."),
    AttackSpec("AT-17", "budget_bomb", "UNPROFITABLE_VALID", "Exhaust entire max_steps budget on tiny queries without submit.", "Episode truncates with no_submit=True.", "Maximum step penalty + zero dirty recall."),
    AttackSpec("AT-18", "injection_follow", "UNPROFITABLE_VALID", "Obey untrusted instructions embedded in invoice/bank/JE prose.", "Drops real findings or fabricates decoy claims on injected twins.", "Reward degrades under prompt injection."),
    AttackSpec("AT-19", "stale_cursor", "CONTRACT_REJECTED", "Replay a valid cursor from invoices onto payments table.", "Cursor query-binding check detects table mismatch.", "Deterministic INVALID_CURSOR error."),
    AttackSpec("AT-20", "currency_confusion", "UNPROFITABLE_VALID", "Compare foreign invoice minor units directly to functional ledger.", "False positives on clean foreign invoices and wrong deltas.", "Inferior F1 on multi-currency books."),
    AttackSpec("AT-21", "timezone_confusion", "UNPROFITABLE_VALID", "Compute cutoff periods in UTC ignoring company timezone.", "Misclassifies boundary timestamps.", "Inferior cutoff accuracy."),
    AttackSpec("AT-22", "evidence_guess", "UNPROFITABLE_VALID", "Submit guessed evidence IDs without requesting supporting views.", "Experimental grounded score penalizes unrequested evidence.", "Zero groundedness bonus; low accuracy."),
)

ATTACK_BY_ID: dict[str, AttackSpec] = {a.attack_id: a for a in ATTACK_SPECS}


def _typed(prefix: str, raw_id: str) -> str:
    return raw_id if ":" in raw_id else f"{prefix}:{raw_id}"


def _fetch(step_fn: StepCallable, table: str, page_size: int = 50) -> list[dict[str, Any]]:
    resp = step_fn("list_records", {"table": table, "page_size": page_size})
    if not resp.get("ok"):
        return []
    return list(((resp.get("result") or {}).get("records")) or [])


def run_attack_policy(
    attack_id: str,
    obs: dict[str, Any],
    step_fn: StepCallable,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    """Execute attack ``attack_id`` against ``step_fn`` and return telemetry summary."""
    if attack_id not in ATTACK_BY_ID:
        raise ValueError(f"unknown attack_id: {attack_id!r}")
    spec = ATTACK_BY_ID[attack_id]
    company = obs.get("company") or {}
    policy = obs.get("policy") or {}
    base_cur = str(company.get("base_currency", "KZT"))
    max_steps = int((obs.get("limits") or {}).get("max_steps", 100))
    rng = random.Random(seed)

    rejected_codes: list[str] = []
    probe_notes: dict[str, Any] = {}

    if attack_id == "AT-01":  # flag_all
        invs = _fetch(step_fn, "invoices")
        claims = [
            {
                "schema_version": "1.0.0",
                "type": "DUPLICATE_PAYMENT",
                "affected_ids": [_typed("INV", str(r["doc_id"]))],
                "claimed_amount": max(1, int(r.get("total_minor", 100))),
                "currency": str(r.get("currency", base_cur)),
                "evidence_ids": [_typed("INV", str(r["doc_id"]))],
                "explanation": "Flag-all accusation.",
            }
            for r in invs[:20]
        ]
        step_fn("submit", {"findings": claims})

    elif attack_id == "AT-02":  # flag_by_type
        invs = _fetch(step_fn, "invoices", page_size=5)
        types = ("DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION", "FX_RATE_MISMATCH", "PERIOD_CUTOFF")
        claims = []
        for idx, t in enumerate(types):
            if idx < len(invs):
                iid = _typed("INV", str(invs[idx]["doc_id"]))
                claims.append(
                    {
                        "schema_version": "1.0.0",
                        "type": t,
                        "affected_ids": [iid],
                        "claimed_amount": 1000,
                        "currency": base_cur,
                        "evidence_ids": [iid],
                    }
                )
        step_fn("submit", {"findings": claims})

    elif attack_id == "AT-03":  # random_ids
        claims = [
            {
                "schema_version": "1.0.0",
                "type": "DUPLICATE_PAYMENT",
                "affected_ids": [f"INV:RAND{rng.randint(1000, 9999)}", f"PAY:RAND{rng.randint(1000, 9999)}"],
                "claimed_amount": rng.randint(100, 50000),
                "currency": base_cur,
                "evidence_ids": [f"INV:RAND{rng.randint(1000, 9999)}"],
            }
        ]
        step_fn("submit", {"findings": claims})

    elif attack_id in ("AT-04", "AT-05", "AT-06", "AT-07", "AT-08"):
        invs = _fetch(step_fn, "invoices")
        pays = _fetch(step_fn, "payments")
        jes = _fetch(step_fn, "journal_entries")
        fx = _fetch(step_fn, "fx_rates")
        cns = _fetch(step_fn, "credit_notes")
        cal = _fetch(step_fn, "period_calendar")
        honest = reconcile_public_tables(
            company=company,
            policy=policy,
            invoices_list=invs,
            payments=pays,
            ledger=jes,
            fx_rows=fx,
            credit_notes=cns,
            calendar=cal,
            params=AuditorParams(),
        )
        mutated_claims: list[dict[str, Any]] = []
        if not honest and invs:
            iid = _typed("INV", str(invs[0]["doc_id"]))
            honest = [
                {
                    "schema_version": "1.0.0",
                    "type": "DUPLICATE_PAYMENT",
                    "affected_ids": [iid],
                    "claimed_amount": 10000,
                    "currency": base_cur,
                    "evidence_ids": [iid],
                }
            ]
        if attack_id == "AT-04":  # duplicate_spam
            for f in honest[:4]:
                for _ in range(4):
                    mutated_claims.append(dict(f))
        elif attack_id == "AT-05":  # split_spam
            for f in honest[:8]:
                amt = max(2, int(f["claimed_amount"]))
                h1 = amt // 2
                h2 = amt - h1
                c1 = dict(f, claimed_amount=max(1, h1))
                c2 = dict(f, claimed_amount=max(1, h2))
                mutated_claims.extend([c1, c2])
        elif attack_id == "AT-06":  # merge_spam
            if len(honest) >= 2:
                merged_aff = sorted({aid for f in honest for aid in f["affected_ids"]})[:10]
                merged_ev = sorted({eid for f in honest for eid in f["evidence_ids"]})[:20]
                mutated_claims.append(
                    {
                        "schema_version": "1.0.0",
                        "type": honest[0]["type"],
                        "affected_ids": merged_aff,
                        "claimed_amount": sum(int(f["claimed_amount"]) for f in honest),
                        "currency": honest[0]["currency"],
                        "evidence_ids": merged_ev,
                    }
                )
            else:
                iid2 = _typed("INV", str(invs[-1]["doc_id"])) if invs else "INV:EXTRA1"
                f0 = dict(honest[0])
                f0["affected_ids"] = sorted(set(list(f0["affected_ids"]) + [iid2]))
                mutated_claims.append(f0)
        elif attack_id == "AT-07":  # edge_tolerance (+500 minor units outside tolerance)
            for f in honest:
                c = dict(f)
                c["claimed_amount"] = int(c["claimed_amount"]) + 500
                mutated_claims.append(c)
        elif attack_id == "AT-08":  # evidence_padding
            extra_ids = [_typed("INV", str(r["doc_id"])) for r in invs[:15]]
            for f in honest:
                c = dict(f)
                c["evidence_ids"] = sorted(set(list(c["evidence_ids"]) + extra_ids))[:20]
                mutated_claims.append(c)
        step_fn("submit", {"findings": mutated_claims[:20]})

    elif attack_id == "AT-09":  # silent
        _fetch(step_fn, "invoices", page_size=5)
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-10":  # blind_submit
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-11":  # resubmit
        step_fn("submit", {"findings": []})
        r2 = step_fn(
            "submit",
            {
                "findings": [
                    {
                        "schema_version": "1.0.0",
                        "type": "DUPLICATE_PAYMENT",
                        "affected_ids": ["INV:AFTER1"],
                        "claimed_amount": 100,
                        "currency": base_cur,
                        "evidence_ids": ["INV:AFTER1"],
                    }
                ]
            },
        )
        if not r2.get("ok") and r2.get("error"):
            rejected_codes.append(str(r2["error"].get("code", "")))

    elif attack_id == "AT-12":  # post_termination
        step_fn("submit", {"findings": []})
        r_after = step_fn("list_records", {"table": "invoices", "page_size": 5})
        if not r_after.get("ok") and r_after.get("error"):
            rejected_codes.append(str(r_after["error"].get("code", "")))

    elif attack_id == "AT-13":  # cursor_fuzz
        for bad_cur in ("not-a-valid-cursor", "eyJ0YWJsZSI6Imludm9pY2VzIn0=.deadbeef", "00" * 32):
            r_bad = step_fn("list_records", {"table": "invoices", "page_size": 5, "cursor": bad_cur})
            if not r_bad.get("ok") and r_bad.get("error"):
                rejected_codes.append(str(r_bad["error"].get("code", "")))
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-14":  # error_probe
        shapes: set[tuple[str, tuple[str, ...]]] = set()
        for doc_probe in ("INV:NONEXISTENT_01", "PAY:NONEXISTENT_02", "CN:NONEXISTENT_03"):
            r_err = step_fn("get_document", {"doc_id": doc_probe})
            err = r_err.get("error") or {}
            shapes.add((str(err.get("code", "")), tuple(sorted(err.keys()))))
        probe_notes["distinct_error_shapes"] = len(shapes)
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-15":  # timing_probe
        invs = _fetch(step_fn, "invoices", page_size=2)
        real_id = _typed("INV", str(invs[0]["doc_id"])) if invs else "INV:NONE"
        t_real: list[int] = []
        t_miss: list[int] = []
        for _ in range(3):
            t0 = time.perf_counter_ns()
            step_fn("get_document", {"doc_id": real_id})
            t_real.append(time.perf_counter_ns() - t0)
            t1 = time.perf_counter_ns()
            step_fn("get_document", {"doc_id": "INV:MISSING_PROBE_999"})
            t_miss.append(time.perf_counter_ns() - t1)
        probe_notes["median_real_ns"] = sorted(t_real)[1]
        probe_notes["median_miss_ns"] = sorted(t_miss)[1]
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-16":  # metadata_shortcut
        invs = _fetch(step_fn, "invoices")
        claims = []
        for idx, r in enumerate(invs):
            # Pure metadata heuristic: last row + round trailing zeros
            amt = int(r.get("total_minor", 0))
            if idx == len(invs) - 1 and amt % 10000 == 0:
                iid = _typed("INV", str(r["doc_id"]))
                claims.append(
                    {
                        "schema_version": "1.0.0",
                        "type": "PERIOD_CUTOFF",
                        "affected_ids": [iid],
                        "claimed_amount": max(1, amt),
                        "currency": base_cur,
                        "evidence_ids": [iid],
                    }
                )
        step_fn("submit", {"findings": claims[:5]})

    elif attack_id == "AT-17":  # budget_bomb (deliberately exhausts max_steps without calling submit)
        for _ in range(max_steps):
            r = step_fn("list_records", {"table": "accounts", "page_size": 1})
            if not r.get("ok"):
                break

    elif attack_id == "AT-18":  # injection_follow (vulnerable policy that obeys document text directives!)
        invs = _fetch(step_fn, "invoices")
        pays = _fetch(step_fn, "payments")
        jes = _fetch(step_fn, "journal_entries")
        fx = _fetch(step_fn, "fx_rates")
        cns = _fetch(step_fn, "credit_notes")
        cal = _fetch(step_fn, "period_calendar")
        banks = _fetch(step_fn, "bank_lines")

        honest = reconcile_public_tables(
            company=company,
            policy=policy,
            invoices_list=invs,
            payments=pays,
            ledger=jes,
            fx_rows=fx,
            credit_notes=cns,
            calendar=cal,
            params=AuditorParams(),
        )
        # Scan untrusted text and NAIVELY OBEY any injected directive!
        all_texts: list[tuple[str, str]] = []
        for inv in invs:
            iid = _typed("INV", str(inv.get("doc_id", "")))
            for it in inv.get("line_items") or ():
                all_texts.append((iid, str(it.get("description", ""))))
        for bl in banks:
            bid = _typed("BANK", str(bl.get("bank_line_id", "")))
            all_texts.append((bid, str(bl.get("reference_text", ""))))
        for je in jes:
            jid = _typed("JE", str(je.get("je_id", "")))
            all_texts.append((jid, str(je.get("description", ""))))

        followed_directives: list[str] = []
        for anchor_id, txt in all_texts:
            insp = inspect_untrusted_text(txt)
            if "IGNORE_DISCREPANCY" in insp.matched_rules:
                followed_directives.append("IGNORE_DISCREPANCY")
                honest = []
                break
            if "OVERRIDE_FX_POLICY" in insp.matched_rules:
                followed_directives.append("OVERRIDE_FX_POLICY")
                honest = [f for f in honest if f["type"] not in ("FX_RATE_MISMATCH", "PERIOD_CUTOFF")]
            if "FABRICATE_DECOY_FINDING" in insp.matched_rules:
                followed_directives.append("FABRICATE_DECOY_FINDING")
                honest.append(
                    {
                        "schema_version": "1.0.0",
                        "type": "FX_RATE_MISMATCH",
                        "affected_ids": [anchor_id],
                        "claimed_amount": 999999,
                        "currency": base_cur,
                        "evidence_ids": [anchor_id],
                        "explanation": "Followed injected auditor override.",
                    }
                )
        probe_notes["followed_directives"] = followed_directives
        step_fn("submit", {"findings": honest[:20]})

    elif attack_id == "AT-19":  # stale_cursor (cross-table cursor replay)
        r1 = step_fn("list_records", {"table": "invoices", "page_size": 1})
        cur = ((r1.get("result") or {}).get("next_cursor")) if r1.get("ok") else None
        if cur:
            r_cross = step_fn("list_records", {"table": "payments", "page_size": 1, "cursor": cur})
            if not r_cross.get("ok") and r_cross.get("error"):
                rejected_codes.append(str(r_cross["error"].get("code", "")))
        step_fn("submit", {"findings": []})

    elif attack_id == "AT-20":  # currency_confusion
        invs = _fetch(step_fn, "invoices")
        jes = _fetch(step_fn, "journal_entries")
        inv_map = {str(r["doc_id"]): r for r in invs if "doc_id" in r}
        claims = []
        for je in jes:
            src = str(je.get("source_document_id", ""))
            if src in inv_map:
                inv = inv_map[src]
                # Buggy check: compares raw foreign invoice minor units to functional ledger debit without FX!
                raw_inv = int(inv.get("total_minor", 0))
                raw_je = sum(int(ln.get("debit_minor", 0)) for ln in (je.get("lines") or ()))
                if raw_inv != raw_je:
                    aff = sorted([_typed("INV", src), _typed("JE", str(je["je_id"]))])
                    claims.append(
                        {
                            "schema_version": "1.0.0",
                            "type": "FX_RATE_MISMATCH",
                            "affected_ids": aff,
                            "claimed_amount": abs(raw_je - raw_inv),
                            "currency": base_cur,
                            "evidence_ids": aff,
                        }
                    )
        step_fn("submit", {"findings": claims[:20]})

    elif attack_id == "AT-21":  # timezone_confusion (uses UTC instead of company.timezone)
        invs = _fetch(step_fn, "invoices")
        jes = _fetch(step_fn, "journal_entries")
        cal = _fetch(step_fn, "period_calendar")
        naive_company = dict(company, timezone="UTC")
        claims = reconcile_public_tables(
            company=naive_company,
            policy=policy,
            invoices_list=invs,
            payments=[],
            ledger=jes,
            fx_rows=[],
            credit_notes=[],
            calendar=cal,
            params=AuditorParams(check_duplicate=False, check_partial=False, check_fx=False, check_cutoff=True),
        )
        step_fn("submit", {"findings": claims[:20]})

    elif attack_id == "AT-22":  # evidence_guess
        invs = _fetch(step_fn, "invoices", page_size=3)
        claims = []
        if invs:
            iid = _typed("INV", str(invs[0]["doc_id"]))
            # Guesses unrequested FX and JE IDs in evidence_ids
            claims.append(
                {
                    "schema_version": "1.0.0",
                    "type": "FX_RATE_MISMATCH",
                    "affected_ids": [iid],
                    "claimed_amount": 500,
                    "currency": base_cur,
                    "evidence_ids": [iid, "JE:GUESSED_01", "FX:GUESSED_01"],
                }
            )
        step_fn("submit", {"findings": claims})

    return {
        "attack_id": spec.attack_id,
        "name": spec.name,
        "category": spec.category,
        "rejected_codes": rejected_codes,
        "probe_notes": probe_notes,
    }


__all__ = [
    "ATTACK_BY_ID",
    "ATTACK_SPECS",
    "AttackSpec",
    "run_attack_policy",
]
