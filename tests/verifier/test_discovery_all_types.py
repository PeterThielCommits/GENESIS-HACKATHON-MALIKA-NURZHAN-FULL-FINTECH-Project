"""Independent discovery tests across clean, all four anomaly types, compound,
on-disk loading, determinism, and unresolved ambiguities (Phase 8, Task 8.2).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from contracts.canonical import canonical_bytes
from contracts.loader import validate_instance
from tests.verifier import fixtures as fx
from verifier import discover, load_public_episode, validate_report
from verifier.public_loader import build_public_episode


class TestDiscoveryAllTypes(unittest.TestCase):
    def test_clean_episode_zero_false_positives(self):
        ep = fx.clean_episode()
        out = discover(ep)
        self.assertEqual(out.report.findings, ())
        self.assertEqual(out.report.unresolved_ambiguities, ())
        self.assertEqual(validate_instance("verifier_report", out.report.to_dict()), [])
        val = validate_report(out.report, public_episode=ep, proof_graph=out.proof_graph)
        self.assertTrue(val.valid, msg=val.errors)

    def test_duplicate_payment_discovered(self):
        ep, truths = fx.duplicate_payment_episode()
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 1)
        f = out.report.findings[0]
        self.assertEqual(f.type, "DUPLICATE_PAYMENT")
        self.assertEqual(f.affected_ids, truths[0].affected_ids)
        self.assertEqual(f.claimed_amount_minor, truths[0].amount_minor)
        self.assertEqual(f.currency, truths[0].currency)
        self.assertEqual(f.evidence_sets, truths[0].evidence_sets)

    def test_partial_allocation_all_subcases(self):
        # Case A: over-allocation (INV-15)
        ep, truths = fx.partial_allocation_episode()
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 1)
        f = out.report.findings[0]
        self.assertEqual(f.type, "PARTIAL_PAYMENT_ALLOCATION")
        self.assertEqual(f.affected_ids, truths[0].affected_ids)
        self.assertEqual(f.claimed_amount_minor, 50000)

        # Case B: unallocated balance when allow_advances=False
        ep_b = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(allow_advances=False),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                {
                    "doc_id": "INV-B1",
                    "counterparty_id": "CP-001",
                    "issue_timestamp": "2025-04-01T10:00:00+05:00",
                    "service_start": "2025-04-01T10:00:00+05:00",
                    "service_end": None,
                    "due_timestamp": "2025-04-20T18:00:00+05:00",
                    "currency": "KZT",
                    "total_minor": 100000,
                    "tax_minor": 0,
                    "line_items": [],
                    "status": "partial",
                }
            ],
            payments=[
                {
                    "pay_id": "PAY-B1",
                    "timestamp": "2025-04-05T10:00:00+05:00",
                    "counterparty_id": "CP-001",
                    "currency": "KZT",
                    "amount_minor": 80000,
                    "allocations": [
                        {
                            "allocation_id": "AL-B1",
                            "document_id": "INV-B1",
                            "amount_minor": 50000,
                            "allocation_timestamp": "2025-04-05T10:00:00+05:00",
                        }
                    ],
                    "bank_reference": None,
                    "payment_channel": "wire",
                }
            ],
        )
        out_b = discover(ep_b)
        self.assertEqual(len(out_b.report.findings), 1)
        self.assertEqual(out_b.report.findings[0].explanation_code, "PARTIAL_ALLOC_UNALLOWED_ADVANCE")
        self.assertEqual(out_b.report.findings[0].claimed_amount_minor, 30000)

        # Case D: wrong counterparty allocation
        ep_d = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                {
                    "doc_id": "INV-D1",
                    "counterparty_id": "CP-002",
                    "issue_timestamp": "2025-04-01T10:00:00+05:00",
                    "service_start": "2025-04-01T10:00:00+05:00",
                    "service_end": None,
                    "due_timestamp": "2025-04-20T18:00:00+05:00",
                    "currency": "KZT",
                    "total_minor": 50000,
                    "tax_minor": 0,
                    "line_items": [],
                    "status": "open",
                }
            ],
            payments=[
                {
                    "pay_id": "PAY-D1",
                    "timestamp": "2025-04-05T10:00:00+05:00",
                    "counterparty_id": "CP-001",
                    "currency": "KZT",
                    "amount_minor": 50000,
                    "allocations": [
                        {
                            "allocation_id": "AL-D1",
                            "document_id": "INV-D1",
                            "amount_minor": 50000,
                            "allocation_timestamp": "2025-04-05T10:00:00+05:00",
                        }
                    ],
                    "bank_reference": None,
                    "payment_channel": "wire",
                }
            ],
        )
        out_d = discover(ep_d)
        self.assertEqual(len(out_d.report.findings), 1)
        self.assertEqual(out_d.report.findings[0].explanation_code, "PARTIAL_ALLOC_WRONG_COUNTERPARTY")
        self.assertEqual(out_d.report.findings[0].affected_ids, ("INV:INV-D1", "PAY:PAY-D1"))

        # Case E: premature invoice closure on partial payment
        ep_e = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                {
                    "doc_id": "INV-E1",
                    "counterparty_id": "CP-001",
                    "issue_timestamp": "2025-04-01T10:00:00+05:00",
                    "service_start": "2025-04-01T10:00:00+05:00",
                    "service_end": None,
                    "due_timestamp": "2025-04-20T18:00:00+05:00",
                    "currency": "KZT",
                    "total_minor": 100000,
                    "tax_minor": 0,
                    "line_items": [],
                    "status": "paid",  # prematurely closed!
                }
            ],
            payments=[
                {
                    "pay_id": "PAY-E1",
                    "timestamp": "2025-04-05T10:00:00+05:00",
                    "counterparty_id": "CP-001",
                    "currency": "KZT",
                    "amount_minor": 60000,
                    "allocations": [
                        {
                            "allocation_id": "AL-E1",
                            "document_id": "INV-E1",
                            "amount_minor": 60000,
                            "allocation_timestamp": "2025-04-05T10:00:00+05:00",
                        }
                    ],
                    "bank_reference": None,
                    "payment_channel": "wire",
                }
            ],
        )
        out_e = discover(ep_e)
        self.assertEqual(len(out_e.report.findings), 1)
        self.assertEqual(out_e.report.findings[0].explanation_code, "PARTIAL_ALLOC_PREMATURE_INVOICE_CLOSED")
        self.assertEqual(out_e.report.findings[0].claimed_amount_minor, 40000)

    def test_fx_mismatch_discovered_with_alternative_evidence(self):
        ep, truths = fx.fx_mismatch_episode()
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 1)
        f = out.report.findings[0]
        self.assertEqual(f.type, "FX_RATE_MISMATCH")
        self.assertEqual(f.affected_ids, ("JE:JE-0301",))
        self.assertEqual(f.claimed_amount_minor, 150000)
        self.assertEqual(f.currency, "KZT")
        self.assertEqual(len(f.evidence_sets), 2)
        self.assertEqual(f.evidence_sets, truths[0].evidence_sets)

    def test_period_cutoff_discovered(self):
        ep, truths = fx.period_cutoff_episode()
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 1)
        f = out.report.findings[0]
        self.assertEqual(f.type, "PERIOD_CUTOFF")
        self.assertEqual(f.affected_ids, ("JE:JE-0401",))
        self.assertEqual(f.claimed_amount_minor, 90000)
        self.assertEqual(f.currency, "KZT")
        self.assertEqual(f.evidence_sets, (("INV:INV-2025-0040", "JE:JE-0401"),))

    def test_compound_four_type_episode(self):
        ep, truths = fx.compound_four_type_episode()
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 4)
        discovered_types = {f.type for f in out.report.findings}
        self.assertEqual(
            discovered_types,
            {
                "DUPLICATE_PAYMENT",
                "PARTIAL_PAYMENT_ALLOCATION",
                "FX_RATE_MISMATCH",
                "PERIOD_CUTOFF",
            },
        )
        self.assertEqual(out.report.unresolved_ambiguities, ())

    def test_disk_load_and_byte_determinism(self):
        ep, _ = fx.compound_four_type_episode()
        with tempfile.TemporaryDirectory() as td:
            pub_dir = Path(td) / "public"
            fx.write_public_dir(pub_dir, ep)
            out1 = discover(pub_dir)
            out2 = discover(load_public_episode(pub_dir))
            self.assertEqual(out1.report_digest, out2.report_digest)
            self.assertEqual(
                canonical_bytes(out1.report.to_dict()),
                canonical_bytes(out2.report.to_dict()),
            )
            self.assertEqual(out1.proof_graph.digest(), out2.proof_graph.digest())

            # Permuting JSON key order on disk preserves episode_public_hash & report_digest
            comp_path = pub_dir / "company.json"
            comp_data = json.loads(comp_path.read_text(encoding="utf-8"))
            reversed_comp = dict(reversed(list(comp_data.items())))
            comp_path.write_text(json.dumps(reversed_comp), encoding="utf-8")
            out3 = discover(pub_dir)
            self.assertEqual(out1.report_digest, out3.report_digest)

    def test_unresolved_ambiguities_not_turned_into_false_findings(self):
        # Missing FX rate with fallback_rule="none" -> ambiguity, zero findings
        ep_missing_fx = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rate_date_rule="operation_date", fallback_rule="none"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            journal_entries=[
                {
                    "je_id": "JE-AMB-1",
                    "timestamp": "2025-04-12T10:00:00+05:00",  # Saturday, no quote
                    "posting_period": "2025-04",
                    "source_document_id": None,
                    "description": "Foreign entry",
                    "lines": [
                        {
                            "line_id": "L1",
                            "account_id": "5010",
                            "debit_minor": 1000,
                            "credit_minor": 0,
                            "currency": "USD",
                            "fx_rate_decimal": "500",
                            "functional_debit_minor": 500000,
                            "functional_credit_minor": 0,
                            "counterparty_id": None,
                            "analytic_tag": None,
                        },
                        {
                            "line_id": "L2",
                            "account_id": "2010",
                            "debit_minor": 0,
                            "credit_minor": 1000,
                            "currency": "USD",
                            "fx_rate_decimal": "500",
                            "functional_debit_minor": 0,
                            "functional_credit_minor": 500000,
                            "counterparty_id": None,
                            "analytic_tag": None,
                        },
                    ],
                }
            ],
            fx_rates=[
                {
                    "fx_id": "FX-FRI",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-11",
                    "rate_decimal": "500.00",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        out = discover(ep_missing_fx)
        self.assertEqual(out.report.findings, ())
        self.assertEqual(len(out.report.unresolved_ambiguities), 1)
        self.assertIn("FX_RATE_UNAVAILABLE", out.report.unresolved_ambiguities[0])

        # Conflicting permitted FX sources on same effective date -> ambiguity, zero findings
        ep_conflict = build_public_episode(
            company=fx.make_company(),
            policy=fx.make_policy(rate_date_rule="operation_date", source_codes=["NBK", "ECB"]),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            journal_entries=list(ep_missing_fx.journal_entries),
            fx_rates=[
                {
                    "fx_id": "FX-SAT-NBK",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-12",
                    "rate_decimal": "500.00",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                },
                {
                    "fx_id": "FX-SAT-ECB",
                    "pair": "USD/KZT",
                    "effective_date": "2025-04-12",
                    "rate_decimal": "510.00",
                    "source_code": "ECB",
                    "publication_timestamp": None,
                },
            ],
        )
        out_c = discover(ep_conflict)
        self.assertEqual(out_c.report.findings, ())
        self.assertEqual(len(out_c.report.unresolved_ambiguities), 1)
        self.assertIn("FX_RATE_CONFLICT", out_c.report.unresolved_ambiguities[0])

    def test_jpy_to_kwd_mixed_exponent_and_compound_same_je_fx_and_cutoff(self):
        # Company functional currency KWD (exp 3); invoice in JPY (exp 0): 1000 JPY
        # Policy rate: 0.002050 KWD/JPY -> expected 2050 KWD minor; booked 2100 KWD minor (FX diff = 50)
        # Also service_start in March 2025, posted in 2025-04 -> PERIOD_CUTOFF (amount = 2100 KWD minor)
        ep = build_public_episode(
            company=fx.make_company(functional_currency="KWD", timezone="Asia/Almaty"),
            policy=fx.make_policy(rate_date_rule="document_date", recognition_event="service_date"),
            accounts=fx.standard_accounts(),
            counterparties=fx.standard_counterparties(),
            invoices=[
                {
                    "doc_id": "INV-JPY-KWD",
                    "counterparty_id": "CP-002",
                    "issue_timestamp": "2025-04-02T10:00:00+05:00",
                    "service_start": "2025-03-30T10:00:00+05:00",
                    "service_end": None,
                    "due_timestamp": "2025-04-20T18:00:00+05:00",
                    "currency": "JPY",
                    "total_minor": 1000,
                    "tax_minor": 0,
                    "line_items": [],
                    "status": "open",
                }
            ],
            journal_entries=[
                {
                    "je_id": "JE-BOTH",
                    "timestamp": "2025-04-02T11:00:00+05:00",
                    "posting_period": "2025-04",
                    "source_document_id": "INV-JPY-KWD",
                    "description": "Book JPY invoice in KWD",
                    "lines": [
                        {
                            "line_id": "L1",
                            "account_id": "5010",
                            "debit_minor": 1000,
                            "credit_minor": 0,
                            "currency": "JPY",
                            "fx_rate_decimal": "0.002100",
                            "functional_debit_minor": 2100,
                            "functional_credit_minor": 0,
                            "counterparty_id": "CP-002",
                            "analytic_tag": None,
                        },
                        {
                            "line_id": "L2",
                            "account_id": "2010",
                            "debit_minor": 0,
                            "credit_minor": 1000,
                            "currency": "JPY",
                            "fx_rate_decimal": "0.002100",
                            "functional_debit_minor": 0,
                            "functional_credit_minor": 2100,
                            "counterparty_id": "CP-002",
                            "analytic_tag": None,
                        },
                    ],
                }
            ],
            fx_rates=[
                {
                    "fx_id": "FX-JPY-KWD-0402",
                    "pair": "JPY/KWD",
                    "effective_date": "2025-04-02",
                    "rate_decimal": "0.002050",
                    "source_code": "NBK",
                    "publication_timestamp": None,
                }
            ],
        )
        out = discover(ep)
        self.assertEqual(len(out.report.findings), 2)
        by_type = {f.type: f for f in out.report.findings}
        self.assertEqual(by_type["FX_RATE_MISMATCH"].claimed_amount_minor, 50)
        self.assertEqual(by_type["FX_RATE_MISMATCH"].currency, "KWD")
        self.assertEqual(
            by_type["FX_RATE_MISMATCH"].evidence_sets,
            (("FX:FX-JPY-KWD-0402", "INV:INV-JPY-KWD", "JE:JE-BOTH"),),
        )
        self.assertEqual(by_type["PERIOD_CUTOFF"].claimed_amount_minor, 2100)
        self.assertEqual(by_type["PERIOD_CUTOFF"].currency, "KWD")
        self.assertEqual(
            by_type["PERIOD_CUTOFF"].evidence_sets,
            (("INV:INV-JPY-KWD", "JE:JE-BOTH"),),
        )
        self.assertTrue(all(ab.all_minimal and ab.all_sufficient for ab in out.ablation_results))

    def test_fresh_process_cli_determinism(self):
        import subprocess
        import sys

        ep, _ = fx.compound_four_type_episode()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pub = root / "public"
            fx.write_public_dir(pub, ep)
            r1 = root / "rep1.json"
            r2 = root / "rep2.json"
            g1 = root / "pg1.json"
            g2 = root / "pg2.json"
            repo_root = Path(__file__).resolve().parent.parent.parent
            p1 = subprocess.run(
                [sys.executable, "-m", "verifier", str(pub), "--out", str(r1), "--proof-graph", str(g1)],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            p2 = subprocess.run(
                [sys.executable, "-m", "verifier", str(pub), "--out", str(r2), "--proof-graph", str(g2)],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(p1.returncode, 0, msg=p1.stderr)
            self.assertEqual(p2.returncode, 0, msg=p2.stderr)
            self.assertEqual(r1.read_bytes(), r2.read_bytes())
            self.assertEqual(g1.read_bytes(), g2.read_bytes())
            self.assertEqual(validate_instance("verifier_report", json.loads(r1.read_text(encoding="utf-8"))), [])


if __name__ == "__main__":
    unittest.main()
