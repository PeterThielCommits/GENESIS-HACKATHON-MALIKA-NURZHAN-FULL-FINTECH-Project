"""Distractor exclusion tests for ALL 16 minimum distractors (TZ 11.6, Task 8.5)
plus counterfactual minimal pairs (TZ 21.2).

Verifies:
  - D-DUP-01..04 produce 0 false positives + explicit ProofGraph exclusions;
  - D-PART-01..04 produce 0 false positives + explicit ProofGraph exclusions;
  - D-FX-01..04 produce 0 false positives + explicit ProofGraph exclusions;
  - D-CUT-01..04 produce 0 false positives + explicit ProofGraph exclusions;
  - Counterfactual minimal pairs (1-fact difference) cleanly separate anomaly
    from clean distractor twin across all four types.
"""

from __future__ import annotations

import unittest

from tests.verifier import fixtures as fx
from verifier import discover
from verifier.public_loader import build_public_episode


def _je(
    je_id: str,
    src_id: str,
    posting_period: str,
    ts: str,
    amt: int,
    cur: str = "KZT",
    fx_rate: str = "1",
    func_amt: int | None = None,
    debit_acc: str = "5010",
    credit_acc: str = "2010",
    analytic_tag: str | None = None,
) -> dict:
    famt = amt if func_amt is None else func_amt
    return {
        "je_id": je_id,
        "timestamp": ts,
        "posting_period": posting_period,
        "source_document_id": src_id,
        "description": f"JE {je_id}",
        "lines": [
            {
                "line_id": "L1",
                "account_id": debit_acc,
                "debit_minor": amt,
                "credit_minor": 0,
                "currency": cur,
                "fx_rate_decimal": fx_rate,
                "functional_debit_minor": famt,
                "functional_credit_minor": 0,
                "counterparty_id": "CP-001",
                "analytic_tag": analytic_tag,
            },
            {
                "line_id": "L2",
                "account_id": credit_acc,
                "debit_minor": 0,
                "credit_minor": amt,
                "currency": cur,
                "fx_rate_decimal": fx_rate,
                "functional_debit_minor": 0,
                "functional_credit_minor": famt,
                "counterparty_id": "CP-001",
                "analytic_tag": analytic_tag,
            },
        ],
    }


def _inv(
    doc_id: str,
    total_minor: int,
    *,
    cur: str = "KZT",
    cp: str = "CP-001",
    issue: str = "2025-04-05T10:00:00+05:00",
    service_start: str = "2025-04-05T09:00:00+05:00",
    service_end: str | None = None,
    status: str = "paid",
    recognition_rule: str | None = None,
    subscription_period: str | None = None,
) -> dict:
    d = {
        "doc_id": doc_id,
        "counterparty_id": cp,
        "issue_timestamp": issue,
        "service_start": service_start,
        "service_end": service_end,
        "due_timestamp": "2025-04-25T18:00:00+05:00",
        "currency": cur,
        "total_minor": total_minor,
        "tax_minor": 0,
        "line_items": [],
        "status": status,
    }
    if recognition_rule is not None:
        d["recognition_rule"] = recognition_rule
    if subscription_period is not None:
        d["subscription_period"] = subscription_period
    return d


def _pay(
    pay_id: str,
    amount_minor: int,
    allocs: list[tuple[str, int]],
    *,
    cur: str = "KZT",
    cp: str = "CP-001",
    ts: str = "2025-04-10T10:00:00+05:00",
    payment_type: str | None = None,
    related_payment_id: str | None = None,
) -> dict:
    d = {
        "pay_id": pay_id,
        "timestamp": ts,
        "counterparty_id": cp,
        "currency": cur,
        "amount_minor": amount_minor,
        "allocations": [
            {
                "allocation_id": f"AL-{pay_id}-{i}",
                "document_id": doc_id,
                "amount_minor": a_amt,
                "allocation_timestamp": ts,
            }
            for i, (doc_id, a_amt) in enumerate(allocs, start=1)
        ],
        "bank_reference": None,
        "payment_channel": "wire",
    }
    if payment_type is not None:
        d["payment_type"] = payment_type
    if related_payment_id is not None:
        d["related_payment_id"] = related_payment_id
    return d


class TestAllSixteenDistractors(unittest.TestCase):
    def _assert_clean_excluded(self, ep, expected_rule_fragment: str):
        out = discover(ep)
        self.assertEqual(
            out.report.findings,
            (),
            msg=f"distractor produced false positive: {out.report.findings}",
        )
        self.assertEqual(out.report.unresolved_ambiguities, ())
        exclusions = out.proof_graph.exclusion_edges()
        self.assertGreater(
            len(exclusions),
            0,
            msg=f"expected explicit ProofGraph exclusion for {expected_rule_fragment}",
        )
        rule_ids = {n.rule_id for n in out.proof_graph.nodes if n.node_type == "RuleNode"}
        self.assertTrue(
            any(expected_rule_fragment in rid for rid in rule_ids),
            msg=f"expected {expected_rule_fragment} in {rule_ids}",
        )

    # ---------------- DUPLICATE_PAYMENT distractors D-DUP-01..04 ----------------
    def test_d_dup_01_credit_adjustment_explains_overpayment(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 50000)],
            payments=[
                _pay("PAY-1", 50000, [("INV-1", 50000)], ts="2025-04-06T10:00:00+05:00"),
                _pay("PAY-2", 50000, [("INV-1", 50000)], ts="2025-04-07T10:00:00+05:00"),
            ],
            credit_notes=[
                {
                    "credit_note_id": "CN-ADJ-1",
                    "invoice_id": "INV-1",
                    "counterparty_id": "CP-001",
                    "timestamp": "2025-04-08T10:00:00+05:00",
                    "amount_minor": 50000,
                    "currency": "KZT",
                    "reason_code": "overpayment_credit",
                }
            ],
        )
        self._assert_clean_excluded(ep, "D-DUP-01")

    def test_d_dup_02_same_amount_two_different_invoices(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-A", 40000), _inv("INV-B", 40000)],
            payments=[
                _pay("PAY-A", 40000, [("INV-A", 40000)], ts="2025-04-06T10:00:00+05:00"),
                _pay("PAY-B", 40000, [("INV-B", 40000)], ts="2025-04-06T11:00:00+05:00"),
            ],
        )
        self._assert_clean_excluded(ep, "D-DUP-02")

    def test_d_dup_03_recurring_subscription_different_periods(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-SUB-MAR",
                    30000,
                    service_start="2025-03-01",
                    service_end="2025-03-31",
                    subscription_period="2025-03",
                ),
                _inv(
                    "INV-SUB-APR",
                    30000,
                    service_start="2025-04-01",
                    service_end="2025-04-30",
                    subscription_period="2025-04",
                ),
            ],
            payments=[
                _pay("PAY-SUB-1", 30000, [("INV-SUB-MAR", 30000)], ts="2025-03-05T10:00:00+05:00"),
                _pay("PAY-SUB-2", 30000, [("INV-SUB-APR", 30000)], ts="2025-04-05T10:00:00+05:00"),
            ],
        )
        self._assert_clean_excluded(ep, "D-DUP-03")

    def test_d_dup_04_valid_refund_reverses_duplicate(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 50000)],
            payments=[
                _pay("PAY-1", 50000, [("INV-1", 50000)], ts="2025-04-06T10:00:00+05:00"),
                _pay("PAY-2", 50000, [("INV-1", 50000)], ts="2025-04-07T10:00:00+05:00"),
                _pay(
                    "PAY-REF-2",
                    -50000,
                    [],
                    ts="2025-04-08T10:00:00+05:00",
                    payment_type="refund",
                    related_payment_id="PAY-2",
                ),
            ],
        )
        self._assert_clean_excluded(ep, "D-DUP-04")

    # ---------------- PARTIAL_PAYMENT_ALLOCATION distractors D-PART-01..04 ----------------
    def test_d_part_01_second_payment_closes_remaining_balance(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 100000, status="paid")],
            payments=[
                _pay("PAY-1", 60000, [("INV-1", 60000)], ts="2025-04-06T10:00:00+05:00"),
                _pay("PAY-2", 40000, [("INV-1", 40000)], ts="2025-04-09T10:00:00+05:00"),
            ],
        )
        self._assert_clean_excluded(ep, "D-PART-01")

    def test_d_part_02_valid_advance_when_allowed(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(allow_advances=True),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 50000, status="paid")],
            payments=[_pay("PAY-ADV", 80000, [("INV-1", 50000)])],
        )
        self._assert_clean_excluded(ep, "D-PART-02")

    def test_d_part_03_valid_multi_invoice_split(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(allow_multi_invoice_split=True),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 30000, status="paid"), _inv("INV-2", 70000, status="paid")],
            payments=[_pay("PAY-SPLIT", 100000, [("INV-1", 30000), ("INV-2", 70000)])],
        )
        self._assert_clean_excluded(ep, "D-PART-03")

    def test_d_part_04_partial_credit_note_closes_remaining_balance(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-1", 100000, status="paid")],
            payments=[_pay("PAY-1", 80000, [("INV-1", 80000)])],
            credit_notes=[
                {
                    "credit_note_id": "CN-PART-1",
                    "invoice_id": "INV-1",
                    "counterparty_id": "CP-001",
                    "timestamp": "2025-04-07T10:00:00+05:00",
                    "amount_minor": 20000,
                    "currency": "KZT",
                    "reason_code": "return",
                }
            ],
        )
        self._assert_clean_excluded(ep, "D-PART-04")

    # ---------------- FX_RATE_MISMATCH distractors D-FX-01..04 ----------------
    def test_d_fx_01_weekend_last_available_fallback(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rate_date_rule="document_date", fallback_rule="last_available"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-WKND",
                    10000,
                    cur="USD",
                    issue="2025-04-12T10:00:00+05:00",  # Saturday
                    service_start="2025-04-12T10:00:00+05:00",
                    status="open",
                )
            ],
            journal_entries=[
                _je("JE-WKND", "INV-WKND", "2025-04", "2025-04-12T10:00:00+05:00", 10000, cur="USD", fx_rate="500.00", func_amt=5000000)
            ],
            fx_rates=[
                {
                    "fx_id": "FX-FRI",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-11",  # Friday
                    "rate_decimal": "500.00",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        self._assert_clean_excluded(ep, "D-FX-01")

    def test_d_fx_02_policy_uses_document_date_not_payment_date(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rate_date_rule="document_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-DOCD",
                    10000,
                    cur="USD",
                    issue="2025-04-10T10:00:00+05:00",
                    service_start="2025-04-10T10:00:00+05:00",
                )
            ],
            payments=[
                _pay("PAY-LATER", 10000, [("INV-DOCD", 10000)], cur="USD", ts="2025-04-15T10:00:00+05:00")
            ],
            journal_entries=[
                _je("JE-DOCD", "INV-DOCD", "2025-04", "2025-04-10T11:00:00+05:00", 10000, cur="USD", fx_rate="500.00", func_amt=5000000)
            ],
            fx_rates=[
                {
                    "fx_id": "FX-0410",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-10",
                    "rate_decimal": "500.00",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                },
                {
                    "fx_id": "FX-0415",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-15",
                    "rate_decimal": "520.00",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                },
            ],
        )
        self._assert_clean_excluded(ep, "D-FX-02")

    def test_d_fx_03_inverse_quote_correctly_inverted(self):
        # Inverse pair KZT/USD = 0.002 -> 100.00 USD (10000 minor) / 0.002 = 5,000,000 KZT minor
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rate_date_rule="document_date", quote_convention="foreign_per_functional"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv("INV-INVQ", 10000, cur="USD", issue="2025-04-10T10:00:00+05:00", service_start="2025-04-10T10:00:00+05:00", status="open")
            ],
            journal_entries=[
                _je("JE-INVQ", "INV-INVQ", "2025-04", "2025-04-10T11:00:00+05:00", 10000, cur="USD", fx_rate="0.002", func_amt=5000000)
            ],
            fx_rates=[
                {
                    "fx_id": "FX-INV-0410",
                    "pair": "KZT/USD",
                    "effective_date": "2025-04-10",
                    "rate_decimal": "0.002",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        self._assert_clean_excluded(ep, "D-FX-03")

    def test_d_fx_04_policy_rounding_half_even_accepted(self):
        # 5 minor USD * 0.5 = 2.5 -> half_even rounds to 2
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rounding_mode="half_even", rate_date_rule="document_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv("INV-RND", 5, cur="USD", issue="2025-04-10T10:00:00+05:00", service_start="2025-04-10T10:00:00+05:00", status="open")
            ],
            journal_entries=[
                _je("JE-RND", "INV-RND", "2025-04", "2025-04-10T11:00:00+05:00", 5, cur="USD", fx_rate="0.5", func_amt=2)
            ],
            fx_rates=[
                {
                    "fx_id": "FX-RND-0410",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-10",
                    "rate_decimal": "0.5",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        self._assert_clean_excluded(ep, "D-FX-04")

    # ---------------- PERIOD_CUTOFF distractors D-CUT-01..04 ----------------
    def test_d_cut_01_utc_date_differs_from_company_local_date(self):
        # 2025-03-31T21:30:00+00:00 -> 2025-04-01T02:30:00+05:00 in Asia/Almaty -> 2025-04
        ep = build_public_episode(
            company=fx.make_company(timezone="Asia/Almaty"),
            policy=fx.make_policy(recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-TZ",
                    50000,
                    issue="2025-04-01T09:00:00+05:00",
                    service_start="2025-03-31T21:30:00+00:00",
                    status="open",
                )
            ],
            journal_entries=[
                _je("JE-TZ", "INV-TZ", "2025-04", "2025-04-01T09:30:00+05:00", 50000)
            ],
        )
        self._assert_clean_excluded(ep, "D-CUT-01")

    def test_d_cut_02_valid_prepayment_excluded(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-PREP",
                    60000,
                    issue="2025-03-20T10:00:00+05:00",
                    service_start="2025-04-10T10:00:00+05:00",
                    status="open",
                )
            ],
            journal_entries=[
                _je(
                    "JE-PREP",
                    "INV-PREP",
                    "2025-03",
                    "2025-03-20T10:30:00+05:00",
                    60000,
                    debit_acc="1410",  # Prepayment asset account
                    credit_acc="1010",
                    analytic_tag="prepayment",
                )
            ],
        )
        self._assert_clean_excluded(ep, "D-CUT-02")

    def test_d_cut_03_service_interval_pro_rata_recognition(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-INT",
                    100000,
                    issue="2025-03-15T10:00:00+05:00",
                    service_start="2025-03-15",
                    service_end="2025-04-15",
                    status="open",
                    recognition_rule="pro_rata",
                )
            ],
            journal_entries=[
                _je("JE-INT-APR", "INV-INT", "2025-04", "2025-04-15T10:00:00+05:00", 50000)
            ],
        )
        self._assert_clean_excluded(ep, "D-CUT-03")

    def test_d_cut_04_late_document_for_earlier_service(self):
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                _inv(
                    "INV-LATE",
                    80000,
                    issue="2025-04-04T10:00:00+05:00",  # April issue
                    service_start="2025-03-28T10:00:00+05:00",  # March service
                    status="open",
                )
            ],
            journal_entries=[
                _je("JE-LATE", "INV-LATE", "2025-03", "2025-04-04T10:30:00+05:00", 80000)
            ],
        )
        self._assert_clean_excluded(ep, "D-CUT-04")

    # ---------------- Counterfactual minimal pairs (TZ 21.2) ----------------
    def test_counterfactual_minimal_pair_duplicate_vs_refund(self):
        err_ep, _ = fx.duplicate_payment_episode()
        # Add single distinguishing fact: a refund reversing PAY-0102
        clean_twin = build_public_episode(
            company=err_ep.company,
            policy=err_ep.policy,
            accounts=err_ep.accounts,
            counterparties=err_ep.counterparties,
            invoices=err_ep.invoices,
            journal_entries=err_ep.journal_entries,
            bank_lines=err_ep.bank_lines,
            payments=list(err_ep.payments)
            + [
                _pay(
                    "PAY-REF-0102",
                    -75000,
                    [],
                    ts="2025-04-12T10:00:00+05:00",
                    payment_type="refund",
                    related_payment_id="PAY-0102",
                )
            ],
        )
        self.assertEqual(len(discover(err_ep).report.findings), 1)
        self.assertEqual(len(discover(clean_twin).report.findings), 0)

    def test_counterfactual_minimal_pair_partial_vs_second_payment(self):
        err_ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-P", 100000, status="paid")],
            payments=[_pay("PAY-P1", 60000, [("INV-P", 60000)], ts="2025-04-06T10:00:00+05:00")],
        )
        clean_twin = build_public_episode(
            company=err_ep.company,
            policy=err_ep.policy,
            accounts=err_ep.accounts,
            counterparties=err_ep.counterparties,
            invoices=err_ep.invoices,
            payments=list(err_ep.payments)
            + [_pay("PAY-P2", 40000, [("INV-P", 40000)], ts="2025-04-09T10:00:00+05:00")],
        )
        self.assertEqual(len(discover(err_ep).report.findings), 1)
        self.assertEqual(len(discover(clean_twin).report.findings), 0)

    def test_counterfactual_minimal_pair_fx_rounding_boundary(self):
        # 5 minor USD * 0.5 = 2.5 -> half_even expects 2 (clean); booked 3 -> FX_RATE_MISMATCH
        base_kwargs = dict(
            company=fx.make_company(),
            policy=fx.make_policy(rounding_mode="half_even", rate_date_rule="document_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-R", 5, cur="USD", issue="2025-04-10T10:00:00+05:00", service_start="2025-04-10T10:00:00+05:00", status="open")],
            fx_rates=[
                {
                    "fx_id": "FX-R",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-10",
                    "rate_decimal": "0.5",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        err_ep = build_public_episode(
            **base_kwargs,
            journal_entries=[_je("JE-R", "INV-R", "2025-04", "2025-04-10T11:00:00+05:00", 5, cur="USD", fx_rate="0.5", func_amt=3)],
        )
        clean_twin = build_public_episode(
            **base_kwargs,
            journal_entries=[_je("JE-R", "INV-R", "2025-04", "2025-04-10T11:00:00+05:00", 5, cur="USD", fx_rate="0.5", func_amt=2)],
        )
        self.assertEqual(len(discover(err_ep).report.findings), 1)
        self.assertEqual(len(discover(clean_twin).report.findings), 0)

    def test_counterfactual_minimal_pair_cutoff_timezone(self):
        # 2025-03-31T21:30:00+00:00 is 2025-04-01 in Asia/Almaty -> 2025-04 clean vs 2025-03 error
        base_kwargs = dict(
            company=fx.make_company(timezone="Asia/Almaty"),
            policy=fx.make_policy(recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[_inv("INV-C", 50000, issue="2025-04-01T09:00:00+05:00", service_start="2025-03-31T21:30:00+00:00", status="open")],
        )
        err_ep = build_public_episode(
            **base_kwargs,
            journal_entries=[_je("JE-C", "INV-C", "2025-03", "2025-04-01T09:30:00+05:00", 50000)],
        )
        clean_twin = build_public_episode(
            **base_kwargs,
            journal_entries=[_je("JE-C", "INV-C", "2025-04", "2025-04-01T09:30:00+05:00", 50000)],
        )
        self.assertEqual(len(discover(err_ep).report.findings), 1)
        self.assertEqual(len(discover(clean_twin).report.findings), 0)


if __name__ == "__main__":
    unittest.main()
