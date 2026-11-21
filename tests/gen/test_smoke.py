"""Smoke tests for the Phase-3 generator scaffold (quick acceptance check).

Uses the standard ``unittest`` module — no third-party dependencies.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gen.rng import NamespacedRNG
from gen.ids import IDFactory
from gen.calendar import fiscal_periods_for_year, period_bounds
from gen.company import generate_company
from gen.chart import generate_chart
from gen.counterparties import generate_counterparties
from gen.fx import generate_fx_rates, rate_for_event, FXError
from gen.invoices import generate_invoices
from gen.credit_notes import generate_credit_notes
from gen.payments import generate_payments
from gen.bank_lines import generate_bank_lines
from gen.journal import build_journal_entries
from gen.policy import build_policy
from gen.invariants.model import catalog, all_invariants


class InvariantsCatalogTest(unittest.TestCase):
    def test_catalog_has_17_invariants(self):
        codes = [inv["code"] for inv in catalog()]
        self.assertEqual(len(codes), 17)
        self.assertEqual(codes, [f"INV-{i:02d}" for i in range(1, 18)])


class RNGTest(unittest.TestCase):
    def test_namespace_deterministic(self):
        a = NamespacedRNG("t", 1).randint(1, 100)
        b = NamespacedRNG("t", 1).randint(1, 100)
        self.assertEqual(a, b)

    def test_interleave_invariance(self):
        r1 = NamespacedRNG("t", 1)
        s1, s2 = NamespacedRNG("a", 1), NamespacedRNG("b", 1)
        r1_seq = [r1.randint(1, 10) for _ in range(5)]
        r2_seq = [r1.randint(1, 10) for _ in range(5)]
        inter = [s1.randint(1, 10) for _ in range(3)] + [s2.randint(1, 10) for _ in range(3)]
        r3 = NamespacedRNG("t", 1)
        r1_seq2 = [r3.randint(1, 10) for _ in range(10)]
        self.assertEqual(r1_seq, r1_seq2[:5])
        self.assertEqual(r2_seq, r1_seq2[5:])


class IDFactoryTest(unittest.TestCase):
    def test_id_factory_unique(self):
        idf = IDFactory(NamespacedRNG("t", 1), 2025)
        ids = {idf.next_je_id() for _ in range(1000)}
        self.assertEqual(len(ids), 1000)

    def test_je_id_format_family_a(self):
        idf = IDFactory(NamespacedRNG("t", 1), 2025)
        self.assertRegex(idf.next_je_id(), r"^JE-\d{6}$")

    def test_inv_id_format_family_a(self):
        idf = IDFactory(NamespacedRNG("t", 1), 2025)
        self.assertRegex(idf.next_inv_id(), r"^INV-2025-\d{4}$")


class CalendarTest(unittest.TestCase):
    def test_period_bounds(self):
        start, end = period_bounds("2025-03", "Asia/Almaty")
        self.assertEqual(start.isoformat(), "2025-03-01")
        self.assertEqual(end.isoformat(), "2025-03-31")


class CompanyTest(unittest.TestCase):
    def test_company_invariants_basic(self):
        c = generate_company(NamespacedRNG("t", 1))
        self.assertEqual(c.timezone, "Asia/Almaty")
        self.assertEqual(c.functional_currency, "KZT")
        self.assertIn("KZT", c.supported_currencies)


class FXTest(unittest.TestCase):
    def test_fx_timeline_deterministic(self):
        r = NamespacedRNG("t", 2)
        c = generate_company(r)
        fx = generate_fx_rates(r, c, fiscal_periods_for_year(2025)[:2])
        r2 = NamespacedRNG("t", 2)
        c2 = generate_company(r2)
        fx2 = generate_fx_rates(r2, c2, fiscal_periods_for_year(2025)[:2])
        self.assertEqual([x.rate_decimal for x in fx], [x.rate_decimal for x in fx2])

    def test_fx_rate_for_event(self):
        r = NamespacedRNG("t", 3)
        c = generate_company(r)
        fx = generate_fx_rates(r, c, fiscal_periods_for_year(2025))
        rate = rate_for_event(fx, "KZT", "USD", "2025-03-15")
        self.assertGreater(rate, 0)


class PipelineTest(unittest.TestCase):
    def test_pipeline_smoke(self):
        r = NamespacedRNG("clean/smoke", 777)
        c = generate_company(r)
        a = generate_chart(r)
        cps = generate_counterparties(r, 6)
        periods = fiscal_periods_for_year(2025)
        fx = generate_fx_rates(r, c, periods)
        pol = build_policy(c, a)
        idf = IDFactory(r, 2025)
        invs = generate_invoices(r, idf, c, cps, periods, n_invoices=8)
        cns = generate_credit_notes(r, idf, invs)
        pays = generate_payments(r, idf, c, invs, cns)
        bls = generate_bank_lines(r, idf, c, pays)
        jes = build_journal_entries(r, idf, c, invs, cns, pays, fx)
        self.assertTrue(all_invariants())
        for je in jes:
            self.assertEqual(
                sum(l.functional_debit_minor for l in je.lines),
                sum(l.functional_credit_minor for l in je.lines),
            )
        self.assertEqual(len(bls), len(pays))
        self.assertEqual(len({i.doc_id for i in invs}), len(invs))


if __name__ == "__main__":
    unittest.main()
