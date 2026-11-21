"""Evidence reachability, minimality, alternative sets, and ablation tests
(Phase 8, Task 8.4 — REQ-VER-010..014, TZ 13.5, 21.3).
"""

from __future__ import annotations

import unittest

from tests.verifier import fixtures as fx
from verifier import (
    VerifierConfig,
    check_evidence_reachability,
    discover,
    subset_public_episode,
    tool_routes_for_typed_id,
)
from verifier.duplicate_payment import detect_duplicate_payments
from verifier.minimal_sets import minimize_evidence_set
from verifier.proof_graph import ProofGraph
from verifier.public_loader import build_public_episode
from verifier.result import VerifierFinding


class TestEvidenceAndAblation(unittest.TestCase):
    def test_all_four_types_pass_ablation_and_reachability(self):
        ep, _ = fx.compound_four_type_episode()
        out = discover(ep, VerifierConfig(run_ablation=True))
        self.assertEqual(len(out.ablation_results), 4)
        for ab in out.ablation_results:
            self.assertTrue(ab.all_sufficient, msg=ab)
            self.assertTrue(ab.all_minimal, msg=ab)
            self.assertTrue(ab.full_deletion_breaks_proof, msg=ab)
            self.assertEqual(ab.failures, ())

        reach = check_evidence_reachability(ep, out.report.findings)
        self.assertTrue(reach.all_reachable, msg=reach.errors)
        for f in out.report.findings:
            for ev_set in f.evidence_sets:
                for eid in ev_set:
                    self.assertTrue(len(tool_routes_for_typed_id(eid)) >= 1)

    def test_single_element_ablation_destroys_proof_for_every_finding(self):
        ep, _ = fx.compound_four_type_episode()
        out = discover(ep, VerifierConfig(run_ablation=True))
        for f in out.report.findings:
            for ev_set in f.evidence_sets:
                # Sufficient as a whole
                sub_full = subset_public_episode(ep, ev_set)
                out_full = discover(sub_full, VerifierConfig(run_ablation=False))
                self.assertIn(
                    f.signature,
                    {x.signature for x in out_full.report.findings},
                    msg=f"evidence set {ev_set} was not sufficient for {f.signature}",
                )
                # Removing ANY single element breaks derivation of exact finding
                for drop in ev_set:
                    reduced = tuple(x for x in ev_set if x != drop)
                    sub_red = subset_public_episode(ep, reduced)
                    out_red = discover(sub_red, VerifierConfig(run_ablation=False))
                    self.assertNotIn(
                        f.signature,
                        {x.signature for x in out_red.report.findings},
                        msg=f"dropping {drop} from {ev_set} did NOT break proof for {f.signature}",
                    )

    def test_redundant_evidence_is_pruned_by_minimizer(self):
        ep, _ = fx.duplicate_payment_episode()
        out = discover(ep, VerifierConfig(run_ablation=False))
        f = out.report.findings[0]
        # Add redundant BANK line and check minimizer strips it cleanly
        bloated = tuple(sorted(set(f.evidence_sets[0]) | {"BANK:BANK-0102"}))
        self.assertEqual(len(bloated), 5)

        def _det(sub_ep, g):
            return detect_duplicate_payments(sub_ep, g).findings

        shrunk = minimize_evidence_set(ep, bloated, f.signature, _det)
        self.assertEqual(shrunk, f.evidence_sets[0])
        self.assertNotIn("BANK:BANK-0102", shrunk)

    def test_alternative_minimal_sets_for_three_payments(self):
        # Invoice 1000, Pay1=1000, Pay2=1000, Pay3=1000 -> Pay3 has TWO minimal prior certificates!
        ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                {
                    "doc_id": "INV-3P",
                    "counterparty_id": "CP-001",
                    "issue_timestamp": "2025-04-01T09:00:00+05:00",
                    "service_start": "2025-04-01T09:00:00+05:00",
                    "service_end": None,
                    "due_timestamp": "2025-04-20T18:00:00+05:00",
                    "currency": "KZT",
                    "total_minor": 1000,
                    "tax_minor": 0,
                    "line_items": [],
                    "status": "paid",
                }
            ],
            payments=[
                {
                    "pay_id": f"PAY-3P-{i}",
                    "timestamp": f"2025-04-0{i + 1}T10:00:00+05:00",
                    "counterparty_id": "CP-001",
                    "currency": "KZT",
                    "amount_minor": 1000,
                    "allocations": [
                        {
                            "allocation_id": f"AL-{i}",
                            "document_id": "INV-3P",
                            "amount_minor": 1000,
                            "allocation_timestamp": f"2025-04-0{i + 1}T10:00:00+05:00",
                        }
                    ],
                    "bank_reference": None,
                    "payment_channel": "wire",
                }
                for i in (1, 2, 3)
            ],
            journal_entries=[
                {
                    "je_id": f"JE-3P-{i}",
                    "timestamp": f"2025-04-0{i + 1}T10:05:00+05:00",
                    "posting_period": "2025-04",
                    "source_document_id": f"PAY-3P-{i}",
                    "description": f"Pay {i}",
                    "lines": [
                        {
                            "line_id": "L1",
                            "account_id": "2010",
                            "debit_minor": 1000,
                            "credit_minor": 0,
                            "currency": "KZT",
                            "fx_rate_decimal": "1",
                            "functional_debit_minor": 1000,
                            "functional_credit_minor": 0,
                            "counterparty_id": "CP-001",
                            "analytic_tag": None,
                        },
                        {
                            "line_id": "L2",
                            "account_id": "1010",
                            "debit_minor": 0,
                            "credit_minor": 1000,
                            "currency": "KZT",
                            "fx_rate_decimal": "1",
                            "functional_debit_minor": 0,
                            "functional_credit_minor": 1000,
                            "counterparty_id": "CP-001",
                            "analytic_tag": None,
                        },
                    ],
                }
                for i in (2, 3)
            ],
        )
        out = discover(ep, VerifierConfig(run_ablation=True))
        self.assertEqual(len(out.report.findings), 2)
        p3_finding = next(f for f in out.report.findings if "PAY:PAY-3P-3" in f.affected_ids)
        self.assertEqual(
            p3_finding.evidence_sets,
            (
                ("INV:INV-3P", "JE:JE-3P-3", "PAY:PAY-3P-1", "PAY:PAY-3P-3"),
                ("INV:INV-3P", "JE:JE-3P-3", "PAY:PAY-3P-2", "PAY:PAY-3P-3"),
            ),
        )
        self.assertTrue(all(ab.all_minimal and ab.all_sufficient for ab in out.ablation_results))

    def test_unreachable_and_oversized_evidence_rejected(self):
        ep = fx.clean_episode()
        bad_finding = VerifierFinding(
            type="PERIOD_CUTOFF",
            affected_ids=("JE:NONEXISTENT",),
            claimed_amount_minor=100,
            currency="KZT",
            evidence_sets=(("JE:NONEXISTENT", "INV:GHOST"),),
            explanation_code="TEST",
        )
        reach = check_evidence_reachability(ep, [bad_finding])
        self.assertFalse(reach.all_reachable)
        self.assertIn("JE:NONEXISTENT", reach.unreachable_ids)
        self.assertIn("INV:GHOST", reach.unreachable_ids)

        # Oversized set against policy max_evidence_ids=2
        tight_ep = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(max_evidence_ids=2),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=list(ep.invoices),
            payments=list(ep.payments),
            journal_entries=list(ep.journal_entries),
            fx_rates=list(ep.fx_rates),
        )
        oversized_finding = VerifierFinding(
            type="FX_RATE_MISMATCH",
            affected_ids=("JE:JE-0002",),
            claimed_amount_minor=100,
            currency="KZT",
            evidence_sets=(("FX:FX-USD-KZT-2025-03-12-NBK", "INV:INV-2025-0002", "JE:JE-0002"),),
            explanation_code="TEST",
        )
        reach2 = check_evidence_reachability(tight_ep, [oversized_finding])
        self.assertFalse(reach2.all_reachable)
        self.assertEqual(len(reach2.oversized_sets), 1)


if __name__ == "__main__":
    unittest.main()
