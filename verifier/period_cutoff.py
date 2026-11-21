"""Independent PERIOD_CUTOFF detector (Zone 3, TZ 9.4, 11.5, 13.6).

Independently resolves each invoice-linked journal entry's recognition
event date in ``company.timezone``, computes the expected fiscal period
(monthly or quarterly, with optional ``period_calendar.json``), and flags
mismatches against ``je.posting_period``.

Emits explicit ProofGraph ``excludes`` paths for distractors D-CUT-01..04:
  - D-CUT-01: UTC date differs from company local date;
  - D-CUT-02: valid prepayment / advance / deferred entry under company policy;
  - D-CUT-03: service interval crossing periods under documented interval rule;
  - D-CUT-04: document issued later for an earlier service period.

Dependencies: ``contracts`` + ``verifier`` stdlib helpers only (never ``gen``).
"""

from __future__ import annotations

from typing import Any

from verifier.duplicate_payment import DetectorResult
from verifier.money_time import (
    compute_fiscal_period,
    require_minor_int,
    to_company_date,
    to_utc_date,
)
from verifier.proof_graph import ProofGraph
from verifier.public_loader import PublicEpisode, make_typed_id
from verifier.result import VerifierFinding

PREPAYMENT_ACCOUNT_TYPES: frozenset[str] = frozenset(
    {"prepayment", "advance", "deferred_revenue", "deferred_expense"}
)
PREPAYMENT_TAGS: frozenset[str] = frozenset(
    {"prepayment", "advance", "deferred"}
)
CASH_OR_SETTLEMENT_ACCOUNT_TYPES: frozenset[str] = frozenset(
    {"cash", "bank", "ap", "ar", "payable", "receivable"}
)


def _is_prepayment_entry(je: dict[str, Any], accounts_by_id: dict[str, dict[str, Any]]) -> bool:
    """Detect valid prepayment/advance/deferred entries from public accounts/tags."""
    lines = list(je.get("lines", ()))
    if not lines:
        return False
    has_prepayment_marker = False
    has_non_prepayment_pnl = False
    for ln in lines:
        tag = str(ln.get("analytic_tag") or "").lower()
        acc = accounts_by_id.get(str(ln.get("account_id", "")), {})
        acc_type = str(acc.get("account_type") or "").lower()
        if tag in PREPAYMENT_TAGS or acc_type in PREPAYMENT_ACCOUNT_TYPES:
            has_prepayment_marker = True
        elif acc_type in ("revenue", "expense", "income", "cogs"):
            has_non_prepayment_pnl = True
    return has_prepayment_marker and not has_non_prepayment_pnl


def detect_period_cutoffs(
    episode: PublicEpisode,
    graph: ProofGraph,
) -> DetectorResult:
    """Independently discover PERIOD_CUTOFF anomalies from public data."""
    findings: list[VerifierFinding] = []
    ambiguities: list[str] = []

    company = episode.company
    cutoff_policy = episode.policy["cutoff_policy"]
    recognition_event = str(cutoff_policy["recognition_event"])
    timezone_source = str(cutoff_policy["timezone_source"])
    if timezone_source != "company":
        raise ValueError(f"unsupported cutoff timezone_source: {timezone_source!r}")

    company_tz = str(company["timezone"])
    fy_start = str(company["fiscal_year_start"])
    period_rule = str(company["fiscal_period_rule"])
    func_cur = str(company["functional_currency"])
    accounts_by_id = episode.accounts_by_id

    cutoff_rule_node = graph.add_rule(
        rule_id="RULE:PERIOD_CUTOFF:INV-09_INV-10",
        payload={
            "invariants": ["INV-09", "INV-10"],
            "recognition_event": recognition_event,
            "timezone_source": timezone_source,
            "company_timezone": company_tz,
            "fiscal_year_start": fy_start,
            "fiscal_period_rule": period_rule,
        },
        source_files=("policy.json", "company.json"),
        label="Period cutoff recognition policy",
    )

    for je in sorted(episode.journal_entries, key=lambda j: str(j["je_id"])):
        je_id = str(je["je_id"])
        je_tid = make_typed_id("JE", je_id)
        src_id = je.get("source_document_id")
        if not isinstance(src_id, str) or not src_id:
            continue
        inv = episode.invoices_by_id.get(src_id)
        if inv is None:
            # Payment or credit-note JE, or invoice absent from subset
            continue

        inv_tid = make_typed_id("INV", src_id)
        je_node = graph.add_record(je_tid, je)
        inv_node = graph.add_record(inv_tid, inv)
        posting_period = str(je["posting_period"])

        # D-CUT-02: Valid prepayment / advance / deferred entry
        if _is_prepayment_entry(je, accounts_by_id):
            prep_rule = graph.add_rule(
                rule_id="RULE:D-CUT-02:PREPAYMENT_DEFERRAL",
                payload={"distractor": "D-CUT-02", "rule": "Prepayment/advance accounts are excluded from revenue/expense cutoff"},
                source_files=("policy.json", "accounts.json"),
            )
            cand_fact = graph.add_fact(
                fact_key=f"cutoff_cand:{je_id}",
                rule_id="RULE:PERIOD_CUTOFF:INV-09_INV-10",
                source_ids=[je_tid, inv_tid],
                parent_node_ids=[je_node, inv_node],
                payload={"je_id": je_id, "posting_period": posting_period, "doc_id": src_id},
            )
            prep_fact = graph.add_fact(
                fact_key=f"d_cut_02:{je_id}",
                rule_id="RULE:D-CUT-02:PREPAYMENT_DEFERRAL",
                source_ids=[je_tid],
                parent_node_ids=[je_node],
                payload={"je_id": je_id, "prepayment_entry": True},
            )
            graph.record_exclusion("D-CUT-02", cand_fact, [prep_fact], rule_node_id=prep_rule, edge_type="excludes")
            continue

        # Determine recognition event timestamp/date
        rec_rule = str(inv.get("recognition_rule") or "").lower()
        event_ts: str | None = None
        if recognition_event == "service_date":
            if rec_rule == "service_end" and inv.get("service_end"):
                event_ts = str(inv["service_end"])
            elif inv.get("service_start"):
                event_ts = str(inv["service_start"])
        elif recognition_event == "issue_date":
            if inv.get("issue_timestamp"):
                event_ts = str(inv["issue_timestamp"])
        elif recognition_event == "delivery_date":
            if inv.get("delivery_timestamp"):
                event_ts = str(inv["delivery_timestamp"])
            elif inv.get("service_end"):
                event_ts = str(inv["service_end"])
        else:
            ambiguities.append(f"CUTOFF_UNKNOWN_RECOGNITION_EVENT:{je_id}:{recognition_event}")
            continue

        if not event_ts:
            ambiguities.append(f"CUTOFF_MISSING_EVENT_DATE:{je_id}:{src_id}:{recognition_event}")
            continue

        local_date = to_company_date(event_ts, company_tz)
        expected_period = compute_fiscal_period(
            local_date, fy_start, period_rule, episode.period_calendar
        )

        # D-CUT-03: Service interval crossing period boundary under documented interval rule
        if inv.get("service_start") and inv.get("service_end"):
            p_start = compute_fiscal_period(
                to_company_date(str(inv["service_start"]), company_tz),
                fy_start,
                period_rule,
                episode.period_calendar,
            )
            p_end = compute_fiscal_period(
                to_company_date(str(inv["service_end"]), company_tz),
                fy_start,
                period_rule,
                episode.period_calendar,
            )
            if p_start != p_end and rec_rule in ("pro_rata", "service_end"):
                valid_interval = (
                    (rec_rule == "pro_rata" and p_start <= posting_period <= p_end)
                    or (rec_rule == "service_end" and posting_period == p_end)
                )
                if valid_interval:
                    d3_rule = graph.add_rule(
                        rule_id="RULE:D-CUT-03:SERVICE_INTERVAL_RECOGNITION",
                        payload={"distractor": "D-CUT-03", "recognition_rule": rec_rule},
                        source_files=("policy.json",),
                    )
                    calc_node = graph.add_calculation(
                        calc_key=f"cutoff_interval:{je_id}",
                        rule_id="RULE:PERIOD_CUTOFF:INV-09_INV-10",
                        source_ids=[je_tid, inv_tid],
                        parent_node_ids=[je_node, inv_node],
                        governed_by_nodes=[cutoff_rule_node],
                        payload={
                            "je_id": je_id,
                            "posting_period": posting_period,
                            "service_start_period": p_start,
                            "service_end_period": p_end,
                            "recognition_rule": rec_rule,
                        },
                    )
                    d3_fact = graph.add_fact(
                        fact_key=f"d_cut_03:{je_id}",
                        rule_id="RULE:D-CUT-03:SERVICE_INTERVAL_RECOGNITION",
                        source_ids=[inv_tid],
                        parent_node_ids=[inv_node],
                        payload={"doc_id": src_id, "recognition_rule": rec_rule, "range": [p_start, p_end]},
                    )
                    graph.record_exclusion("D-CUT-03", calc_node, [d3_fact], rule_node_id=d3_rule, edge_type="excludes")
                    continue

        calc_node = graph.add_calculation(
            calc_key=f"cutoff_check:{je_id}",
            rule_id="RULE:PERIOD_CUTOFF:INV-09_INV-10",
            source_ids=[je_tid, inv_tid],
            parent_node_ids=[je_node, inv_node],
            governed_by_nodes=[cutoff_rule_node],
            payload={
                "je_id": je_id,
                "doc_id": src_id,
                "recognition_event": recognition_event,
                "event_timestamp": event_ts,
                "company_local_date": local_date.isoformat(),
                "expected_period": expected_period,
                "posting_period": posting_period,
            },
            label=f"Cutoff check for {je_tid} ({posting_period} vs {expected_period})",
        )

        if posting_period == expected_period:
            # D-CUT-01: UTC period differs from company local period
            utc_d = to_utc_date(event_ts)
            if utc_d is not None:
                utc_period = compute_fiscal_period(
                    utc_d, fy_start, period_rule, episode.period_calendar
                )
                if utc_period != expected_period:
                    d1_rule = graph.add_rule(
                        rule_id="RULE:D-CUT-01:COMPANY_TIMEZONE_BOUNDARY",
                        payload={"distractor": "D-CUT-01", "company_timezone": company_tz},
                        source_files=("company.json", "policy.json"),
                    )
                    d1_fact = graph.add_fact(
                        fact_key=f"d_cut_01:{je_id}",
                        rule_id="RULE:D-CUT-01:COMPANY_TIMEZONE_BOUNDARY",
                        source_ids=[inv_tid, je_tid],
                        parent_node_ids=[inv_node, je_node],
                        payload={"utc_period": utc_period, "company_period": expected_period},
                    )
                    graph.record_exclusion("D-CUT-01", calc_node, [d1_fact], rule_node_id=d1_rule, edge_type="excludes")

            # D-CUT-04: Late issue date differs from earlier service date
            if recognition_event == "service_date" and inv.get("issue_timestamp"):
                issue_period = compute_fiscal_period(
                    to_company_date(str(inv["issue_timestamp"]), company_tz),
                    fy_start,
                    period_rule,
                    episode.period_calendar,
                )
                if issue_period != expected_period:
                    d4_rule = graph.add_rule(
                        rule_id="RULE:D-CUT-04:LATE_ISSUE_FOR_EARLIER_SERVICE",
                        payload={"distractor": "D-CUT-04", "recognition_event": recognition_event},
                        source_files=("policy.json",),
                    )
                    d4_fact = graph.add_fact(
                        fact_key=f"d_cut_04:{je_id}",
                        rule_id="RULE:D-CUT-04:LATE_ISSUE_FOR_EARLIER_SERVICE",
                        source_ids=[inv_tid, je_tid],
                        parent_node_ids=[inv_node, je_node],
                        payload={"issue_period": issue_period, "service_period": expected_period},
                    )
                    graph.record_exclusion("D-CUT-04", calc_node, [d4_fact], rule_node_id=d4_rule, edge_type="excludes")
            continue

        # Cutoff violation: compute functional period amount moved out of expected_period
        lines = list(je.get("lines", ()))
        amount_minor = sum(
            require_minor_int(ln["functional_debit_minor"], "line.functional_debit_minor")
            for ln in lines
        )
        affected = (je_tid,)
        evidence = tuple(sorted([inv_tid, je_tid]))
        finding_node_id = graph.add_finding(
            finding_key=f"PERIOD_CUTOFF:{je_id}",
            rule_id="RULE:PERIOD_CUTOFF:INV-09_INV-10",
            source_ids=evidence,
            supporting_node_ids=[calc_node],
            governed_by_nodes=[cutoff_rule_node],
            payload={
                "type": "PERIOD_CUTOFF",
                "affected_ids": list(affected),
                "claimed_amount_minor": amount_minor,
                "currency": func_cur,
                "expected_period": expected_period,
                "posting_period": posting_period,
            },
            label=f"Period cutoff error on {je_tid}",
        )

        findings.append(
            VerifierFinding(
                type="PERIOD_CUTOFF",
                affected_ids=affected,
                claimed_amount_minor=amount_minor,
                currency=func_cur,
                evidence_sets=(evidence,),
                explanation_code="PERIOD_CUTOFF_WRONG_POSTING_PERIOD",
                proof_graph_ref=f"proof:{finding_node_id}",
                evidence_enumeration_complete=True,
            )
        )

    return DetectorResult(findings=tuple(findings), ambiguities=tuple(ambiguities))


__all__ = ["detect_period_cutoffs"]
