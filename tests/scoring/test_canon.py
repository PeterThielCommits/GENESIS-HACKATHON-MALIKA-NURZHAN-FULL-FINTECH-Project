"""Canonical typed IDs and finding validation tests (Phase 6 task 6.2).

Covers TZ 15.1: NFC normalisation, namespace checks, sorting,
deduplication, rejection of unknown/ambiguous IDs, schema-boundary
validation of findings and truths (REQ-CONTRACT-002).
"""

from __future__ import annotations

import unicodedata
import unittest

from contracts.loader import validate_instance
from contracts.models import Finding, TruthFinding
from scoring.canon import (
    NAMESPACES,
    ScoringInputError,
    canonical_id,
    canonical_id_set,
    canonicalize_finding,
    canonicalize_truth,
    parse_typed_id,
    validate_findings,
    validate_truths,
)
from tests.scoring import fixtures as fx


class TestParseTypedId(unittest.TestCase):
    def test_valid_ids(self):
        self.assertEqual(parse_typed_id("JE:001"), ("JE", "001"))
        self.assertEqual(parse_typed_id("INV:2024/07/0001"), ("INV", "2024/07/0001"))
        self.assertEqual(parse_typed_id("PAY:a-b_c.d"), ("PAY", "a-b_c.d"))
        self.assertEqual(parse_typed_id("BANK:zz"), ("BANK", "zz"))
        self.assertEqual(parse_typed_id("FX:1"), ("FX", "1"))
        self.assertEqual(parse_typed_id("CN:9"), ("CN", "9"))
        self.assertEqual(parse_typed_id("CP:x"), ("CP", "x"))

    def test_ascii_alphabet_enforced(self):
        # The frozen schema ID alphabet is ASCII; NFC forms with accents
        # are rejected as malformed, never silently repaired.
        decomposed = unicodedata.normalize("NFD", "PAY:caf\u00e9")
        composed = unicodedata.normalize("NFC", "PAY:caf\u00e9")
        self.assertNotEqual(decomposed, composed)
        for raw in (decomposed, composed):
            with self.subTest(raw=raw):
                with self.assertRaises(ScoringInputError):
                    parse_typed_id(raw)

    def test_nfc_normalisation_is_applied(self):
        # A pure-ASCII ID is a fixed point of NFC; the canonical form is
        # stable under repeated normalisation (REQ-CONTRACT-012).
        raw = "INV:2024-07/0001"
        self.assertEqual(
            unicodedata.normalize("NFC", raw),
            canonical_id(unicodedata.normalize("NFC", raw)),
        )

    def test_unknown_namespace(self):
        with self.assertRaises(ScoringInputError) as ctx:
            parse_typed_id("XX:001")
        self.assertIn("unknown typed-ID namespace", str(ctx.exception))

    def test_malformed_and_ambiguous(self):
        for raw in ("JE:", ":x", "JE", "je:x", "JE:a:b", "JE:has space", "", "JE:*"):
            with self.subTest(raw=raw):
                with self.assertRaises(ScoringInputError):
                    parse_typed_id(raw)

    def test_non_string(self):
        with self.assertRaises(ScoringInputError):
            parse_typed_id(123)  # type: ignore[arg-type]

    def test_namespaces_match_schema(self):
        self.assertEqual(NAMESPACES, ("JE", "INV", "CN", "PAY", "BANK", "FX", "CP"))


class TestCanonicalIdSet(unittest.TestCase):
    def test_sorted_and_deduped(self):
        result = canonical_id_set(["PAY:b", "INV:z", "PAY:b", "PAY:a"])
        self.assertEqual(result, ("INV:z", "PAY:a", "PAY:b"))

    def test_namespaces_never_collide(self):
        result = canonical_id_set(["JE:x", "PAY:x"])
        self.assertEqual(result, ("JE:x", "PAY:x"))

    def test_prefixes_kept(self):
        self.assertEqual(canonical_id("JE:001"), "JE:001")

    def test_invalid_member_rejected(self):
        with self.assertRaises(ScoringInputError):
            canonical_id_set(["PAY:ok", "NOPE:bad"])

    def test_idempotent(self):
        once = canonical_id_set(["PAY:b", "PAY:a"])
        twice = canonical_id_set(once)
        self.assertEqual(once, twice)


class TestFindingValidation(unittest.TestCase):
    def test_canonicalize_sorts_ids(self):
        f = fx.finding(affected_ids=("PAY:002", "PAY:001"), evidence_ids=("JE:2", "JE:1"))
        canon = canonicalize_finding(f)
        self.assertEqual(canon.affected_ids, ("PAY:001", "PAY:002"))
        self.assertEqual(canon.evidence_ids, ("JE:1", "JE:2"))

    def test_schema_rejects_unknown_type(self):
        f = Finding(
            type="SOMETHING_ELSE",
            affected_ids=("PAY:001",),
            claimed_amount=1,
            currency="KZT",
            evidence_ids=("JE:1",),
        )
        with self.assertRaises(ScoringInputError):
            canonicalize_finding(f)

    def test_schema_rejects_untyped_ids(self):
        f = Finding(
            type="DUPLICATE_PAYMENT",
            affected_ids=("001",),
            claimed_amount=1,
            currency="KZT",
            evidence_ids=("JE:1",),
        )
        with self.assertRaises(ScoringInputError):
            canonicalize_finding(f)

    def test_rejects_empty_evidence(self):
        f = fx.finding(evidence_ids=())
        with self.assertRaises(ScoringInputError):
            canonicalize_finding(f)

    def test_rejects_bool_amount(self):
        f = Finding(
            type="DUPLICATE_PAYMENT",
            affected_ids=("PAY:001",),
            claimed_amount=True,  # type: ignore[arg-type]
            currency="KZT",
            evidence_ids=("JE:1",),
        )
        with self.assertRaises(ScoringInputError):
            canonicalize_finding(f)

    def test_rejects_non_integer_amount(self):
        f = Finding(
            type="DUPLICATE_PAYMENT",
            affected_ids=("PAY:001",),
            claimed_amount=1.5,  # type: ignore[arg-type]
            currency="KZT",
            evidence_ids=("JE:1",),
        )
        with self.assertRaises(ScoringInputError):
            canonicalize_finding(f)

    def test_boundary_rejects_extra_field(self):
        f = fx.finding()
        raw = f.to_dict()
        raw["bonus"] = 1
        errors = validate_instance("finding", raw)
        self.assertTrue(errors, "schema must reject unknown fields")

    def test_validate_findings_reports_index(self):
        good = fx.finding()
        bad = fx.finding(affected_ids=())
        with self.assertRaises(ScoringInputError) as ctx:
            validate_findings([good, bad])
        self.assertIn("finding[1]", str(ctx.exception))

    def test_validate_findings_rejects_wrong_types(self):
        with self.assertRaises(ScoringInputError):
            validate_findings(["not a finding"])  # type: ignore[list-item]


class TestTruthValidation(unittest.TestCase):
    def test_truth_round_trip(self):
        t = fx.partial_alloc_truth()
        canon = canonicalize_truth(t)
        self.assertEqual(
            canon.evidence_sets, (("INV:020", "PAY:030"), ("INV:020", "JE:055"))
        )

    def test_truth_rejects_negative_tolerance(self):
        t = fx.truth(tolerance_minor=-1)
        with self.assertRaises(ScoringInputError):
            canonicalize_truth(t)

    def test_truth_rejects_empty_evidence_sets(self):
        t = TruthFinding(
            truth_id="T",
            type="DUPLICATE_PAYMENT",
            affected_ids=("PAY:001",),
            amount_minor=1,
            currency="KZT",
            tolerance_minor=0,
            evidence_sets=(),
            minimal_evidence_size=1,
            invariant_signature={},
            operator_version="x@1",
        )
        with self.assertRaises(ScoringInputError):
            canonicalize_truth(t)

    def test_validate_truths_reports_index(self):
        with self.assertRaises(ScoringInputError) as ctx:
            validate_truths([fx.truth(), "nope"])  # type: ignore[list-item]
        self.assertIn("truth[1]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
