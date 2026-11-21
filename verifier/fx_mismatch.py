"""Independent FX_RATE_MISMATCH detector (Zone 3, TZ 9.3, 11.4, 13.6).

Independently implements:
  - FX rate date selection from ``policy.fx_policy.rate_date_rule``;
  - Quote filtering by ``source_codes``, pair orientation, and ``fallback_rule``
    (``last_available`` vs ``none``);
  - Exact rational currency conversion with single policy rounding
    (``half_even`` / ``half_up``) and exact quote inversion;
  - Unresolved ambiguity reporting when required quotes are missing or
    permitted sources conflict on the selected date (REQ-VER-005);
  - Explicit ProofGraph ``excludes`` paths for distractors D-FX-01..04.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from verifier.duplicate_payment import DetectorResult
from verifier.money_time import (
    FxConversionResult,
    convert_minor_with_pair,
    require_minor_int,
    to_company_date,
)
from verifier.proof_graph import ProofGraph
from verifier.public_loader import (
    PublicEpisode,
    fx_row_typed_id,
    make_typed_id,
)
from verifier.result import MAX_SCHEMA_EVIDENCE_SETS, VerifierFinding


def _resolve_fx_target_date(
    je: dict[str, Any],
    episode: PublicEpisode,
    rate_date_rule: str,
    company_tz: str,
    payments_by_invoice: dict[str, list[dict[str, Any]]],
) -> tuple[date | None, tuple[str, ...], str | None, bool]:
    """Return ``(target_date, source_typed_ids, ambiguity_msg, doc_vs_pay_distinct)``.

    ``doc_vs_pay_distinct`` is True when ``rate_date_rule == "document_date"``
    and a linked payment exists on a different company-local date (D-FX-02).
    """
    je_id = str(je["je_id"])
    src_id = je.get("source_document_id")

    if rate_date_rule == "operation_date":
        return to_company_date(str(je["timestamp"]), company_tz), (), None, False

    if not isinstance(src_id, str) or not src_id:
        return to_company_date(str(je["timestamp"]), company_tz), (), None, False

    inv = episode.invoices_by_id.get(src_id)
    pay = episode.payments_by_id.get(src_id)
    cn = episode.credit_notes_by_id.get(src_id)

    if rate_date_rule == "document_date":
        if inv is not None:
            doc_date = to_company_date(str(inv["issue_timestamp"]), company_tz)
            inv_tid = make_typed_id("INV", src_id)
            linked_pays = payments_by_invoice.get(src_id, ())
            pay_dates = {
                to_company_date(str(p["timestamp"]), company_tz) for p in linked_pays
            }
            doc_vs_pay = any(pd != doc_date for pd in pay_dates)
            return doc_date, (inv_tid,), None, doc_vs_pay
        if cn is not None:
            cn_date = to_company_date(str(cn["timestamp"]), company_tz)
            return cn_date, (make_typed_id("CN", src_id),), None, False
        if pay is not None:
            allocs = pay.get("allocations", ())
            alloc_doc_ids = sorted({str(a["document_id"]) for a in allocs if a.get("document_id")})
            if not alloc_doc_ids:
                return to_company_date(str(pay["timestamp"]), company_tz), (make_typed_id("PAY", src_id),), None, False
            inv_dates: dict[date, list[str]] = {}
            missing_invs: list[str] = []
            for d in alloc_doc_ids:
                linked_inv = episode.invoices_by_id.get(d)
                if linked_inv is None:
                    missing_invs.append(d)
                    continue
                d_date = to_company_date(str(linked_inv["issue_timestamp"]), company_tz)
                inv_dates.setdefault(d_date, []).append(make_typed_id("INV", d))
            if missing_invs:
                return None, (), f"FX_SOURCE_DOC_MISSING:{je_id}:{','.join(missing_invs)}", False
            if len(inv_dates) > 1:
                return None, (), f"FX_MULTI_INVOICE_DOC_DATE_AMBIGUOUS:{je_id}", False
            only_date, inv_tids = next(iter(inv_dates.items()))
            pay_date = to_company_date(str(pay["timestamp"]), company_tz)
            return (
                only_date,
                tuple(sorted([make_typed_id("PAY", src_id)] + inv_tids)),
                None,
                pay_date != only_date,
            )
        # Source document referenced by JE is not present in this episode/subset
        return None, (), f"FX_SOURCE_DOC_MISSING:{je_id}:{src_id}", False

    if rate_date_rule == "payment_date":
        if pay is not None:
            return to_company_date(str(pay["timestamp"]), company_tz), (make_typed_id("PAY", src_id),), None, False
        if inv is not None:
            linked_pays = payments_by_invoice.get(src_id, ())
            if not linked_pays:
                return None, (), f"FX_PAYMENT_DATE_UNAVAILABLE:{je_id}:{src_id}", False
            pay_dates = {
                to_company_date(str(p["timestamp"]), company_tz): p for p in linked_pays
            }
            if len(pay_dates) > 1:
                return None, (), f"FX_MULTI_PAYMENT_DATE_AMBIGUOUS:{je_id}:{src_id}", False
            p_date, p_row = next(iter(pay_dates.items()))
            return (
                p_date,
                tuple(sorted([make_typed_id("INV", src_id), make_typed_id("PAY", str(p_row["pay_id"]))])),
                None,
                False,
            )
        if cn is not None:
            return to_company_date(str(cn["timestamp"]), company_tz), (make_typed_id("CN", src_id),), None, False
        return None, (), f"FX_SOURCE_DOC_MISSING:{je_id}:{src_id}", False

    return None, (), f"FX_UNKNOWN_RATE_DATE_RULE:{je_id}:{rate_date_rule}", False


def _select_permitted_quotes(
    fx_rates: tuple[dict[str, Any], ...],
    foreign_currency: str,
    functional_currency: str,
    target_date: date,
    source_codes: frozenset[str],
    fallback_rule: str,
) -> tuple[date | None, list[dict[str, Any]]]:
    """Independently select policy-permitted FX rows for ``target_date``."""
    valid_pairs = {
        f"{foreign_currency}/{functional_currency}",
        f"{functional_currency}/{foreign_currency}",
    }
    candidates: list[tuple[date, dict[str, Any]]] = []
    for row in fx_rates:
        if str(row.get("source_code", "")) not in source_codes:
            continue
        if str(row.get("pair", "")) not in valid_pairs:
            continue
        eff = date.fromisoformat(str(row["effective_date"]))
        if fallback_rule == "none":
            if eff == target_date:
                candidates.append((eff, row))
        elif fallback_rule == "last_available":
            if eff <= target_date:
                candidates.append((eff, row))
        else:
            raise ValueError(f"unsupported fallback_rule: {fallback_rule!r}")

    if not candidates:
        return None, []
    selected_date = max(d for d, _ in candidates)
    selected_rows = sorted(
        [row for d, row in candidates if d == selected_date],
        key=lambda r: fx_row_typed_id(r),
    )
    return selected_date, selected_rows


def detect_fx_mismatches(
    episode: PublicEpisode,
    graph: ProofGraph,
    *,
    max_evidence_sets: int = MAX_SCHEMA_EVIDENCE_SETS,
) -> DetectorResult:
    """Independently discover FX_RATE_MISMATCH anomalies from public data."""
    findings: list[VerifierFinding] = []
    ambiguities: list[str] = []

    func_cur = str(episode.company["functional_currency"])
    company_tz = str(episode.company["timezone"])
    fxp = episode.policy["fx_policy"]
    rate_date_rule = str(fxp["rate_date_rule"])
    fallback_rule = str(fxp["fallback_rule"])
    source_codes = frozenset(str(c) for c in fxp["source_codes"])
    quote_convention = str(fxp["quote_convention"])
    rounding_mode = str(episode.policy["rounding_mode"])

    # Index positive payments by invoice for document/payment date cross-reference
    payments_by_invoice: dict[str, list[dict[str, Any]]] = {}
    for pay in episode.payments:
        if type(pay.get("amount_minor")) is int and pay["amount_minor"] > 0:
            for alloc in pay.get("allocations", ()):
                d = str(alloc.get("document_id", ""))
                if d:
                    payments_by_invoice.setdefault(d, []).append(pay)

    fx_rule_node = graph.add_rule(
        rule_id="RULE:FX_POLICY:INV-07_INV-08",
        payload={
            "invariants": ["INV-07", "INV-08"],
            "functional_currency": func_cur,
            "rate_date_rule": rate_date_rule,
            "fallback_rule": fallback_rule,
            "source_codes": sorted(source_codes),
            "quote_convention": quote_convention,
            "rounding_mode": rounding_mode,
        },
        source_files=("policy.json", "company.json"),
        label="FX rate selection and recalculation policy",
    )

    for je in sorted(episode.journal_entries, key=lambda j: str(j["je_id"])):
        je_id = str(je["je_id"])
        je_tid = make_typed_id("JE", je_id)
        lines = list(je.get("lines", ()))
        foreign_lines = [ln for ln in lines if str(ln.get("currency", func_cur)) != func_cur]
        if not foreign_lines:
            continue

        target_date, date_source_tids, amb_msg, doc_vs_pay_distinct = _resolve_fx_target_date(
            je, episode, rate_date_rule, company_tz, payments_by_invoice
        )
        if amb_msg is not None or target_date is None:
            if amb_msg:
                ambiguities.append(amb_msg)
            continue

        # Group foreign lines by foreign currency
        foreign_currencies = sorted({str(ln["currency"]) for ln in foreign_lines})

        # Evaluate each foreign currency independently; collect per-currency permitted quotes
        per_cur_quotes: dict[str, tuple[date, list[dict[str, Any]]]] = {}
        unresolved = False
        for fcur in foreign_currencies:
            sel_date, sel_rows = _select_permitted_quotes(
                episode.fx_rates, fcur, func_cur, target_date, source_codes, fallback_rule
            )
            if sel_date is None or not sel_rows:
                ambiguities.append(
                    f"FX_RATE_UNAVAILABLE:{je_id}:{fcur}/{func_cur}:{target_date.isoformat()}"
                )
                unresolved = True
                break
            per_cur_quotes[fcur] = (sel_date, sel_rows)
        if unresolved:
            continue

        # Recalculate every foreign line under every permitted quote for its currency;
        # reject/mark ambiguous if two permitted quotes yield different rounded functional amounts.
        expected_debit_total = 0
        expected_credit_total = 0
        booked_debit_total = 0
        booked_credit_total = 0
        any_inverted = False
        any_fractional_round = False
        any_weekend_fallback = False
        chosen_quotes_per_cur: dict[str, list[dict[str, Any]]] = {}

        for fcur in foreign_currencies:
            sel_date, sel_rows = per_cur_quotes[fcur]
            if sel_date < target_date:
                any_weekend_fallback = True
            cur_lines = [ln for ln in foreign_lines if str(ln["currency"]) == fcur]

            quote_outcomes: list[tuple[dict[str, Any], list[tuple[FxConversionResult, FxConversionResult]]]] = []
            for qrow in sel_rows:
                pair = str(qrow["pair"])
                rate_str = str(qrow["rate_decimal"])
                line_res: list[tuple[FxConversionResult, FxConversionResult]] = []
                for ln in cur_lines:
                    d_amt = require_minor_int(ln["debit_minor"], "line.debit_minor")
                    c_amt = require_minor_int(ln["credit_minor"], "line.credit_minor")
                    d_conv = convert_minor_with_pair(d_amt, fcur, func_cur, pair, rate_str, rounding_mode)
                    c_conv = convert_minor_with_pair(c_amt, fcur, func_cur, pair, rate_str, rounding_mode)
                    line_res.append((d_conv, c_conv))
                quote_outcomes.append((qrow, line_res))

            # Verify all permitted quotes agree on every line's rounded functional amount
            first_signature = [
                (dc.rounded_minor, cc.rounded_minor) for dc, cc in quote_outcomes[0][1]
            ]
            conflict = False
            for _, other_res in quote_outcomes[1:]:
                sig = [(dc.rounded_minor, cc.rounded_minor) for dc, cc in other_res]
                if sig != first_signature:
                    conflict = True
                    break
            if conflict:
                ambiguities.append(
                    f"FX_RATE_CONFLICT:{je_id}:{fcur}/{func_cur}:{sel_date.isoformat()}"
                )
                unresolved = True
                break

            chosen_quotes_per_cur[fcur] = [q for q, _ in quote_outcomes]
            for ln, (dc, cc) in zip(cur_lines, quote_outcomes[0][1]):
                expected_debit_total += dc.rounded_minor
                expected_credit_total += cc.rounded_minor
                booked_debit_total += require_minor_int(ln["functional_debit_minor"], "functional_debit_minor")
                booked_credit_total += require_minor_int(ln["functional_credit_minor"], "functional_credit_minor")
                if dc.inverted or cc.inverted:
                    any_inverted = True
                if dc.exact_minor.denominator > 1 or cc.exact_minor.denominator > 1:
                    any_fractional_round = True

        if unresolved:
            continue

        debit_diff = abs(booked_debit_total - expected_debit_total)
        credit_diff = abs(booked_credit_total - expected_credit_total)
        misstatement = max(debit_diff, credit_diff)

        je_node = graph.add_record(je_tid, je)
        source_doc_nodes: list[str] = []
        for dtid in date_source_tids:
            ns, _, local = dtid.partition(":")
            if ns == "INV" and local in episode.invoices_by_id:
                source_doc_nodes.append(graph.add_record(dtid, episode.invoices_by_id[local]))
            elif ns == "PAY" and local in episode.payments_by_id:
                source_doc_nodes.append(graph.add_record(dtid, episode.payments_by_id[local]))
            elif ns == "CN" and local in episode.credit_notes_by_id:
                source_doc_nodes.append(graph.add_record(dtid, episode.credit_notes_by_id[local]))

        all_fx_tids: list[str] = []
        all_fx_nodes: list[str] = []
        for fcur in foreign_currencies:
            for qrow in chosen_quotes_per_cur[fcur]:
                ftid = fx_row_typed_id(qrow)
                all_fx_tids.append(ftid)
                all_fx_nodes.append(graph.add_record(ftid, qrow))

        calc_node = graph.add_calculation(
            calc_key=f"fx_recalc:{je_id}",
            rule_id="RULE:FX_POLICY:INV-07_INV-08",
            source_ids=[je_tid] + list(date_source_tids) + all_fx_tids,
            parent_node_ids=[je_node] + source_doc_nodes + all_fx_nodes,
            governed_by_nodes=[fx_rule_node],
            payload={
                "je_id": je_id,
                "target_date": target_date.isoformat(),
                "booked_functional_debit_minor": booked_debit_total,
                "expected_functional_debit_minor": expected_debit_total,
                "booked_functional_credit_minor": booked_credit_total,
                "expected_functional_credit_minor": expected_credit_total,
                "misstatement_minor": misstatement,
                "functional_currency": func_cur,
            },
            label=f"FX recalculation for {je_tid}",
        )

        if misstatement == 0:
            # Record explicit distractor exclusions in ProofGraph (D-FX-01..04)
            if any_weekend_fallback:
                r1 = graph.add_rule(
                    rule_id="RULE:D-FX-01:WEEKEND_LAST_AVAILABLE",
                    payload={"distractor": "D-FX-01", "fallback_rule": fallback_rule},
                    source_files=("policy.json",),
                )
                f1 = graph.add_fact(
                    fact_key=f"d_fx_01:{je_id}",
                    rule_id="RULE:D-FX-01:WEEKEND_LAST_AVAILABLE",
                    source_ids=all_fx_tids,
                    parent_node_ids=all_fx_nodes,
                    payload={"target_date": target_date.isoformat(), "fallback_rule": fallback_rule},
                )
                graph.record_exclusion("D-FX-01", calc_node, [f1], rule_node_id=r1, edge_type="excludes")
            if doc_vs_pay_distinct:
                r2 = graph.add_rule(
                    rule_id="RULE:D-FX-02:DOCUMENT_DATE_POLICY",
                    payload={"distractor": "D-FX-02", "rate_date_rule": rate_date_rule},
                    source_files=("policy.json",),
                )
                f2 = graph.add_fact(
                    fact_key=f"d_fx_02:{je_id}",
                    rule_id="RULE:D-FX-02:DOCUMENT_DATE_POLICY",
                    source_ids=list(date_source_tids) + all_fx_tids,
                    parent_node_ids=source_doc_nodes + all_fx_nodes,
                    payload={"rate_date_rule": rate_date_rule, "target_date": target_date.isoformat()},
                )
                graph.record_exclusion("D-FX-02", calc_node, [f2], rule_node_id=r2, edge_type="excludes")
            if any_inverted:
                r3 = graph.add_rule(
                    rule_id="RULE:D-FX-03:INVERSE_QUOTE_CONVERSION",
                    payload={"distractor": "D-FX-03", "quote_convention": quote_convention},
                    source_files=("policy.json",),
                )
                f3 = graph.add_fact(
                    fact_key=f"d_fx_03:{je_id}",
                    rule_id="RULE:D-FX-03:INVERSE_QUOTE_CONVERSION",
                    source_ids=all_fx_tids,
                    parent_node_ids=all_fx_nodes,
                    payload={"inverted": True, "quote_convention": quote_convention},
                )
                graph.record_exclusion("D-FX-03", calc_node, [f3], rule_node_id=r3, edge_type="excludes")
            if any_fractional_round:
                r4 = graph.add_rule(
                    rule_id="RULE:D-FX-04:POLICY_ROUNDING_ACCEPTABLE",
                    payload={"distractor": "D-FX-04", "rounding_mode": rounding_mode},
                    source_files=("policy.json",),
                )
                f4 = graph.add_fact(
                    fact_key=f"d_fx_04:{je_id}",
                    rule_id="RULE:D-FX-04:POLICY_ROUNDING_ACCEPTABLE",
                    source_ids=[je_tid] + all_fx_tids,
                    parent_node_ids=[je_node] + all_fx_nodes,
                    payload={"rounding_mode": rounding_mode, "exact_match_after_rounding": True},
                )
                graph.record_exclusion("D-FX-04", calc_node, [f4], rule_node_id=r4, edge_type="excludes")
            continue

        # Build alternative minimal evidence sets (Cartesian product across currencies if multiple quotes agree)
        combo_lists: list[list[str]] = [[]]
        complete = True
        for fcur in foreign_currencies:
            f_tids = [fx_row_typed_id(q) for q in chosen_quotes_per_cur[fcur]]
            next_combos: list[list[str]] = []
            for prefix in combo_lists:
                for ftid in f_tids:
                    next_combos.append(prefix + [ftid])
                    if len(next_combos) >= max_evidence_sets:
                        complete = False
                        break
                if len(next_combos) >= max_evidence_sets:
                    break
            combo_lists = next_combos

        evidence_sets: list[tuple[str, ...]] = []
        base_ids = [je_tid] + list(date_source_tids)
        for fx_choice in combo_lists:
            ev = tuple(sorted(set(base_ids) | set(fx_choice)))
            if ev not in evidence_sets:
                evidence_sets.append(ev)
        evidence_sets.sort(key=lambda s: (len(s), s))

        affected = (je_tid,)
        finding_node_id = graph.add_finding(
            finding_key=f"FX_RATE_MISMATCH:{je_id}",
            rule_id="RULE:FX_POLICY:INV-07_INV-08",
            source_ids=sorted({eid for s in evidence_sets for eid in s}),
            supporting_node_ids=[calc_node],
            governed_by_nodes=[fx_rule_node],
            payload={
                "type": "FX_RATE_MISMATCH",
                "affected_ids": list(affected),
                "claimed_amount_minor": misstatement,
                "currency": func_cur,
            },
            label=f"FX rate mismatch on {je_tid}",
        )

        findings.append(
            VerifierFinding(
                type="FX_RATE_MISMATCH",
                affected_ids=affected,
                claimed_amount_minor=misstatement,
                currency=func_cur,
                evidence_sets=tuple(evidence_sets[:max_evidence_sets]),
                explanation_code="FX_RATE_POLICY_MISMATCH",
                proof_graph_ref=f"proof:{finding_node_id}",
                evidence_enumeration_complete=complete,
            )
        )

    return DetectorResult(findings=tuple(findings), ambiguities=tuple(ambiguities))


__all__ = ["detect_fx_mismatches"]
