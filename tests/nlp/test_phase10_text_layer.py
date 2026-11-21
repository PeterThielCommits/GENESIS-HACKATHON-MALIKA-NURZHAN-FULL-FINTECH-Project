"""Phase 10 quality-closure tests — MULTILINGUAL TEXT / NLP LAYER.

Covers the six Phase-10 tasks end to end (Master TZ §17, §24):

  10.1 deterministic ru/kk/en templates + pinned dictionary versions;
  10.2 abbreviations, transliteration, benign typos with protected typed IDs;
  10.3 Unicode normalization edge cases (zero-width, bidi, homoglyphs, NFC);
  10.4 text-to-entity candidate matching stays an optional hypothesis helper;
  10.5 evidence hierarchy enforcement: no text-only findings can earn reward;
  10.6 explanation consistency report artifact (tools/explanation_report.py).

EXIT GATE 10 evidence:
  - text layer off/on never changes core semantics (cross-checked with
    tests/generator/test_rng_isolation.py);
  - verifier/scoring never rely on unsupported fuzzy matches (AST boundary
    scan + subprocess import checks below).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

from contracts.models import Finding, TruthFinding
from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin
from gen.core.rng import scoped_rng
from gen.core.text import (
    _BANK_REF_TEMPLATES,
    TEMPLATE_DICTIONARY_VERSION,
    TEXT_LAYER_VERSION,
    _apply_controlled_ocr_noise,
    apply_multilingual_text_layer,
)
from nlp import (
    TextOnlyProofRejectedError,
    assess_evidence_reachability,
    build_evidence_hierarchy_report,
    extract_typed_id_mentions,
    normalize_nfc,
    require_structural_proof,
    text_similarity_bps,
    transliterate_to_ascii_skeleton,
)
from scoring.diagnostics import (
    NOT_AVAILABLE_EVIDENCE_HIERARCHY,
    build_diagnostics,
)
from scoring.matcher import REASON_EVIDENCE, match_predicate, optimal_matching
from scoring.reward import compute_reward

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _generate_texted(seed: int = 4242, *, language_profile: str = "mixed", noise_level: int = 0, attempt: int = 1):
    spec = CleanTwinSpec(episode_id="ep_phase10_txt", master_seed=seed, episode_index=0)
    twin = generate_clean_twin(spec)
    rng = scoped_rng(seed, "text_layer", "ep_phase10_txt", attempt)
    meta = apply_multilingual_text_layer(twin, rng, language_profile=language_profile, noise_level=noise_level)
    return twin, meta


def _text_snapshot(twin) -> list[tuple[str, str, str]]:
    """(table, record id, text) for every descriptive text field."""
    rows: list[tuple[str, str, str]] = []
    for cp in twin.counterparties:
        rows.append(("counterparties", str(cp["counterparty_id"]), str(cp["name"])))
        for alias in cp.get("aliases") or ():
            rows.append(("counterparties", str(cp["counterparty_id"]), str(alias)))
    for inv in twin.invoices:
        for item in inv.get("line_items", []):
            rows.append(("invoices", str(inv["doc_id"]), str(item["description"])))
    for bl in twin.bank_lines:
        rows.append(("bank_lines", str(bl["bank_line_id"]), str(bl.get("reference_text", ""))))
        rows.append(("bank_lines", str(bl["bank_line_id"]), str(bl.get("counterparty_text", ""))))
    for cn in twin.credit_notes:
        rows.append(("credit_notes", str(cn["credit_note_id"]), str(cn["reason"])))
    for je in twin.journal_entries:
        rows.append(("journal_entries", str(je["je_id"]), str(je["description"])))
    return rows


class TestPhase10DeterministicTemplates(unittest.TestCase):
    """Task 10.1 — deterministic ru/kk/en templates with pinned dictionary versions."""

    def test_same_seed_config_yields_byte_identical_text(self) -> None:
        t1, m1 = _generate_texted(seed=4242, language_profile="mixed", noise_level=2)
        t2, m2 = _generate_texted(seed=4242, language_profile="mixed", noise_level=2)
        self.assertEqual(_text_snapshot(t1), _text_snapshot(t2))
        self.assertEqual(m1, m2)

    def test_different_seed_changes_text(self) -> None:
        t1, _ = _generate_texted(seed=4242)
        t2, _ = _generate_texted(seed=4243)
        self.assertNotEqual(_text_snapshot(t1), _text_snapshot(t2))

    def test_dictionary_versions_pinned_and_recorded_in_meta(self) -> None:
        _, meta = _generate_texted()
        self.assertEqual(meta["text_layer_version"], TEXT_LAYER_VERSION)
        self.assertEqual(meta["dictionary_version"], TEMPLATE_DICTIONARY_VERSION)
        self.assertEqual(TEXT_LAYER_VERSION, "text-layer@1.0.0")
        self.assertEqual(TEMPLATE_DICTIONARY_VERSION, "ru-kk-en-dicts@1.0.0")

    def test_language_profiles_render_each_language(self) -> None:
        for profile in ("en", "ru", "kk", "mixed"):
            twin, meta = _generate_texted(seed=777, language_profile=profile)
            self.assertEqual(meta["language_profile"], profile)
            self.assertTrue(_text_snapshot(twin))
        with self.assertRaises(ValueError):
            apply_multilingual_text_layer(
                generate_clean_twin(CleanTwinSpec(episode_id="x", master_seed=1, episode_index=0)),
                scoped_rng(1, "text_layer", "x", 1),
                language_profile="de",
            )

    def test_invalid_noise_level_rejected(self) -> None:
        with self.assertRaises(ValueError):
            apply_multilingual_text_layer(
                generate_clean_twin(CleanTwinSpec(episode_id="x", master_seed=1, episode_index=0)),
                scoped_rng(1, "text_layer", "x", 1),
                noise_level=3,
            )


class TestPhase10AbbreviationsTyposTransliteration(unittest.TestCase):
    """Task 10.2 — abbreviations, transliteration, benign typos."""

    def test_abbreviated_business_forms_present_in_bank_ref_templates(self) -> None:
        markers = {"ru": ("сч/ф", "Пл. пор.", "согл."), "en": ("Pmt", "inv.", "ref"), "kk": ("ш/ф", "ТТК", "тапсырмасы")}
        for lang, forms in markers.items():
            joined = " || ".join(_BANK_REF_TEMPLATES[lang])
            for form in forms:
                self.assertIn(form, joined, f"{lang} templates must keep business abbreviation {form!r}")

    def test_benign_typos_applied_deterministically_and_preserve_typed_ids(self) -> None:
        twin, _ = _generate_texted(seed=9090, noise_level=2)
        # Protected doc references inside bank narratives must survive byte-exact.
        pay_by_bank = {str(p.get("bank_reference")): p for p in twin.payments if p.get("bank_reference")}
        checked = 0
        for bl in twin.bank_lines:
            linked = pay_by_bank.get(str(bl.get("bank_line_id", "")))
            if not linked:
                continue
            allocs = linked.get("allocations") or []
            if not allocs:
                continue
            doc_ref = str(allocs[0].get("document_id", ""))
            if doc_ref:
                self.assertIn(doc_ref, str(bl.get("reference_text", "")))
                checked += 1
        self.assertGreater(checked, 0, "expected at least one linked bank narrative with a protected doc id")
        # Journal descriptions embed source_document_id — also protected.
        je_checked = 0
        for je in twin.journal_entries:
            src = str(je.get("source_document_id") or "")
            if src:
                self.assertIn(src, str(je["description"]))
                je_checked += 1
        self.assertGreater(je_checked, 0)

    def test_controlled_ocr_noise_unit(self) -> None:
        import random

        rng = random.Random(1)
        text = "Оплата по счету INV-ABC123DEF456 за услуги"
        noisy = _apply_controlled_ocr_noise(text, rng, ("INV-ABC123DEF456",))
        self.assertIn("INV-ABC123DEF456", noisy)
        self.assertEqual(noisy, unicodedata.normalize("NFC", noisy))
        # Deterministic for the same rng seed.
        self.assertEqual(
            noisy,
            _apply_controlled_ocr_noise(text, random.Random(1), ("INV-ABC123DEF456",)),
        )

    def test_transliteration_skeleton_shared_across_scripts(self) -> None:
        # Same word order in source => identical ASCII skeleton across scripts.
        self.assertEqual(
            transliterate_to_ascii_skeleton('«Алтын Орда» ЖШС'),
            transliterate_to_ascii_skeleton("Altyn Orda LLP"),
        )
        # Different legal-form position still shares the same skeleton tokens.
        self.assertEqual(
            sorted(transliterate_to_ascii_skeleton('ТОО «Алтын Орда»').split()),
            sorted(transliterate_to_ascii_skeleton("Altyn Orda LLP").split()),
        )
        self.assertTrue(transliterate_to_ascii_skeleton('«Жетісу Агро» ЖШС').isascii())


class TestPhase10UnicodeNormalization(unittest.TestCase):
    """Task 10.3 — Unicode normalization tests (REQ-NLP-005)."""

    def test_zero_width_and_bidi_controls_stripped(self) -> None:
        poisoned = "INV\u200b:1\u202e0\u200d0\ufeff1 \u2060x"
        cleaned = normalize_nfc(poisoned)
        for ch in ("\u200b", "\u202e", "\u200d", "\ufeff", "\u2060"):
            self.assertNotIn(ch, cleaned)

    def test_nfd_input_renormalized_to_nfc(self) -> None:
        s = "Алтын Орда"
        nfd = unicodedata.normalize("NFD", s)
        self.assertEqual(normalize_nfc(nfd), unicodedata.normalize("NFC", s))

    def test_homoglyph_lookalike_ids_are_not_extracted_as_typed_ids(self) -> None:
        # Cyrillic 'а' inside the local part must NOT yield a typed-ID mention.
        self.assertEqual(extract_typed_id_mentions("см. INV:1а23 за период"), ())
        self.assertEqual(extract_typed_id_mentions("см. INV:ab1а23"), ())
        self.assertEqual(extract_typed_id_mentions("см. INV:1001 и PAY:2001"), ("INV:1001", "PAY:2001"))

    def test_text_layer_output_is_always_nfc(self) -> None:
        for seed in (11, 22, 33):
            for noise in (0, 1, 2):
                twin, _ = _generate_texted(seed=seed, noise_level=noise)
                for _table, _rid, text in _text_snapshot(twin):
                    self.assertEqual(text, unicodedata.normalize("NFC", text))


class TestPhase10OptionalEntityMatching(unittest.TestCase):
    """Task 10.4 + EXIT GATE — candidate matching optional; core never relies on fuzzy NLP."""

    def test_candidate_matches_are_hypothesis_tier_only(self) -> None:
        from nlp import rank_counterparty_candidates

        cps = [{"counterparty_id": "CP:1", "name": "Altyn Orda LLP", "aliases": ['ТОО "Алтын Орда"']}]
        cands = rank_counterparty_candidates("Алтын Орда ЖШС", cps)
        self.assertTrue(cands)
        for c in cands:
            self.assertTrue(c.requires_structured_verification)
            self.assertIn(c.tier, ("TIER_3_VERIFIED_ALIAS_SURFACE", "TIER_4_TEXT_SIMILARITY_ONLY"))

    def test_core_modules_load_no_nlp_submodules(self) -> None:
        code = (
            "import sys, gen.pipeline, env.environment, verifier, scoring.matcher, scoring.reward, "
            "scoring.diagnostics, seal.merkle, seal.receipt, harness.protocol; "
            "mods = sorted(m for m in sys.modules if m == 'nlp' or m.startswith('nlp.')); "
            "assert mods == [], mods"
        )
        res = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_scorer_loads_only_strict_hierarchy_rule_module(self) -> None:
        code = (
            "import sys, scoring.scorer_cli; "
            "mods = sorted(m for m in sys.modules if m == 'nlp' or m.startswith('nlp.')); "
            "assert set(mods) <= {'nlp', 'nlp.hierarchy'}, mods"
        )
        res = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_similarity_is_symmetric_and_bounded(self) -> None:
        a, b = "Төлем тапсырмасы INV:1001", "Tolem tapsyrmasy INV:1001"
        s1 = text_similarity_bps(a, b)
        s2 = text_similarity_bps(b, a)
        self.assertEqual(s1, s2)
        self.assertTrue(0 <= s1 <= 10000)


class TestPhase10EvidenceHierarchyEnforcement(unittest.TestCase):
    """Task 10.5 — evidence hierarchy enforced; text-only findings inadmissible."""

    @staticmethod
    def _truth() -> TruthFinding:
        return TruthFinding.from_dict(
            {
                "schema_version": "1.0.0",
                "truth_id": "T-P10-01",
                "type": "DUPLICATE_PAYMENT",
                "affected_ids": ["INV:10", "PAY:20"],
                "amount_minor": 25000,
                "currency": "KZT",
                "tolerance_minor": 0,
                "evidence_sets": [["INV:10", "PAY:20"]],
                "evidence_enumeration_complete": True,
                "minimal_evidence_size": 2,
                "invariant_signature": {"invariant_id": "INV-04"},
                "operator_version": "gen-operators@1.0.0",
            }
        )

    def test_reachability_tiers(self) -> None:
        t1 = assess_evidence_reachability(
            evidence_ids=["INV:10", "PAY:20"], affected_ids=["INV:10", "PAY:20"], accessible_public_ids={"INV:10", "PAY:20"}
        )
        self.assertEqual(t1.strongest_tier, 1)
        self.assertTrue(t1.admissible_for_submission)

        t2 = assess_evidence_reachability(
            evidence_ids=["BANK:9"], affected_ids=["INV:10"], accessible_public_ids={"BANK:9", "INV:10"}
        )
        self.assertEqual(t2.strongest_tier, 2)
        self.assertTrue(t2.admissible_for_submission)

        t3 = assess_evidence_reachability(
            evidence_ids=["BANK:9", "CP:ghost"], affected_ids=["INV:10"], accessible_public_ids={"BANK:9", "INV:10"}
        )
        self.assertEqual(t3.strongest_tier, 3)
        self.assertFalse(t3.admissible_for_submission)

        t4 = assess_evidence_reachability(evidence_ids=["CP:ghost"], affected_ids=["INV:10"], accessible_public_ids={"INV:10"})
        self.assertEqual(t4.strongest_tier, 4)
        self.assertFalse(t4.admissible_for_submission)

        t_empty = assess_evidence_reachability(evidence_ids=[], affected_ids=["INV:10"], accessible_public_ids={"INV:10"})
        self.assertEqual(t_empty.strongest_tier, 4)
        self.assertFalse(t_empty.admissible_for_submission)

    def test_text_only_finding_rejected_by_guard_and_earns_zero_reward(self) -> None:
        truth = self._truth()
        # Structurally-correct claim, but proof cites only unreachable "evidence";
        # the narrative name-drops truth IDs and amounts to fish for credit.
        finding = Finding(
            type="DUPLICATE_PAYMENT",
            affected_ids=("INV:10", "PAY:20"),
            claimed_amount=25000,
            currency="KZT",
            evidence_ids=("CP:ghost",),
            explanation="INV:10 and PAY:20 duplicated for 25000 KZT — see narrative.",
        )
        verdict = assess_evidence_reachability(
            evidence_ids=finding.evidence_ids,
            affected_ids=finding.affected_ids,
            accessible_public_ids={"INV:10", "PAY:20"},
        )
        self.assertFalse(verdict.admissible_for_submission)
        with self.assertRaises(TextOnlyProofRejectedError):
            require_structural_proof(verdict)

        decision = match_predicate(finding, truth)
        self.assertFalse(decision.matched)
        self.assertEqual(decision.reason, REASON_EVIDENCE)

        mr = optimal_matching([finding], [truth])
        rb = compute_reward([finding], [truth], 12, match_result=mr)
        self.assertEqual(mr.tp, 0)
        self.assertAlmostEqual(float(rb.precision), 0.0)

    def test_structural_finding_is_admissible_and_matches(self) -> None:
        truth = self._truth()
        finding = Finding(
            type="DUPLICATE_PAYMENT",
            affected_ids=("INV:10", "PAY:20"),
            claimed_amount=25000,
            currency="KZT",
            evidence_ids=("INV:10", "PAY:20"),
            explanation="Duplicate posting INV:10 / PAY:20 for 25000 KZT.",
        )
        verdict = assess_evidence_reachability(
            evidence_ids=finding.evidence_ids,
            affected_ids=finding.affected_ids,
            accessible_public_ids={"INV:10", "PAY:20"},
        )
        self.assertTrue(verdict.admissible_for_submission)
        require_structural_proof(verdict)  # must not raise
        self.assertTrue(match_predicate(finding, truth).matched)

    def test_hierarchy_report_and_diagnostics_passthrough(self) -> None:
        findings = [
            Finding(
                type="DUPLICATE_PAYMENT",
                affected_ids=("INV:10", "PAY:20"),
                claimed_amount=25000,
                currency="KZT",
                evidence_ids=("INV:10", "PAY:20"),
            ),
            Finding(
                type="DUPLICATE_PAYMENT",
                affected_ids=("INV:11",),
                claimed_amount=1,
                currency="KZT",
                evidence_ids=("CP:ghost",),
            ),
        ]
        rep = build_evidence_hierarchy_report(findings, accessible_public_ids={"INV:10", "PAY:20"})
        self.assertEqual(rep["status"], "EVALUATED")
        self.assertTrue(rep["diagnostic_only"])
        self.assertFalse(rep["affects_official_reward"])
        self.assertEqual(rep["findings_checked"], 2)
        self.assertEqual(rep["admissible_count"], 1)
        self.assertEqual(rep["inadmissible_count"], 1)
        self.assertFalse(rep["all_admissible"])

        mr = optimal_matching(findings, [])
        rb = compute_reward(findings, [], 2, match_result=mr)
        diag = build_diagnostics(findings, [], mr, rb, run_info={"steps_used": 2, "evidence_hierarchy": rep})
        self.assertEqual(diag["evidence_hierarchy"]["status"], "EVALUATED")
        diag_missing = build_diagnostics(findings, [], mr, rb, run_info={"steps_used": 2})
        self.assertEqual(diag_missing["evidence_hierarchy"], NOT_AVAILABLE_EVIDENCE_HIERARCHY)


class TestPhase10ExplanationConsistencyReport(unittest.TestCase):
    """Task 10.6 — explanation consistency report artifact."""

    def test_demo_report_covers_all_rules_and_is_diagnostic(self) -> None:
        from tools.explanation_report import main

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "explanation_consistency_report.json"
            rc = main(["--demo", "--output", str(out)])
            self.assertEqual(rc, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["report_type"], "explanation_consistency")
        self.assertTrue(report["diagnostic_only"])
        self.assertFalse(report["affects_official_reward"])
        self.assertEqual({r["rule_id"] for r in report["rules"]}, {"EC-01", "EC-02", "EC-03", "EC-04", "EC-05"})
        self.assertEqual(report["findings_checked"], 5)
        self.assertEqual(report["consistent_count"], 2)
        self.assertEqual(report["inconsistent_count"], 3)
        self.assertFalse(report["all_consistent"])

    def test_report_matches_linter_for_submission_input(self) -> None:
        from scoring.explanation_linter import lint_findings_explanations
        from tools.explanation_report import build_explanation_consistency_report, main

        findings = [
            Finding(
                type="DUPLICATE_PAYMENT",
                affected_ids=("INV:1001", "PAY:2001"),
                claimed_amount=125000,
                currency="KZT",
                evidence_ids=("INV:1001", "PAY:2001"),
                explanation="Duplicate on INV:1001 for 125000 KZT.",
            )
        ]
        direct = build_explanation_consistency_report(findings, source="unit")
        self.assertEqual(direct["per_finding"], lint_findings_explanations(findings)["per_finding"])

        with tempfile.TemporaryDirectory() as td:
            sub = Path(td) / "submission.json"
            sub.write_text(json.dumps({"findings": [f.to_dict() for f in findings]}), encoding="utf-8")
            out = Path(td) / "report.json"
            rc = main(["--submission", str(sub), "--output", str(out)])
            self.assertEqual(rc, 0)
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["source"], f"submission:{sub.as_posix()}")
        self.assertEqual(report["findings_checked"], 1)
        self.assertTrue(report["all_consistent"])


if __name__ == "__main__":
    unittest.main()
