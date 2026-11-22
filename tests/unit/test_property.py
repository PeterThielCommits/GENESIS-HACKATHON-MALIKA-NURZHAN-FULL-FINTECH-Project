"""Stdlib property loops (TZ §20.2 fallback when Hypothesis is absent).

Deterministic loops supplement the other §20.2 test suites. Hypothesis-based
tests (Phase 13, task 13.5) run only when the optional ``hypothesis`` extra is
installed; otherwise they are explicitly SKIPPED (REQ-UNIQUE-003: core never
requires Hypothesis). D-13-01 adds the missing §20.2 loops (money rounding,
JE balance, FX determinism, cutoff timezone, scoring bounds, duplicate TP).
"""

import hashlib
import random
import unittest

from contracts.canonical import canonical_json, sha256_hex
from contracts.models import canonical_ids
from seal.hashchain import HashChainBuilder, verify_hash_chain
from seal.merkle import MerkleTree, verify_inclusion_proof


class TestStdlibProperties(unittest.TestCase):
    def test_canonical_stable_under_key_permutation(self):
        rng = random.Random(42)
        base = {"a": 1, "b": [1, 2, 3], "c": {"x": "y", "n": 7}, "d": "text"}
        keys = list(base.keys())
        for _ in range(50):
            rng.shuffle(keys)
            permuted = {k: base[k] for k in keys}
            self.assertEqual(canonical_json(base), canonical_json(permuted))
            self.assertEqual(sha256_hex(base), sha256_hex(permuted))

    def test_canonical_ids_idempotent(self):
        ids = ["JE:b", "JE:a", "PAY:x", "JE:a"]
        once = canonical_ids(ids)
        twice = canonical_ids(list(once))
        self.assertEqual(once, twice)
        self.assertEqual(list(once), sorted(set(ids)))

    def test_money_int_preserved(self):
        # Money stays int through canonical round-trip (REQ-MONEY-001).
        import json

        payload = {"amount_minor": 123456, "currency": "KZT"}
        parsed = json.loads(canonical_json(payload))
        self.assertIsInstance(parsed["amount_minor"], int)
        self.assertEqual(parsed["amount_minor"], 123456)

    def test_merkle_tree_inclusion_property_across_sizes(self):
        # Deterministic property loop across leaf counts 1..25 (REQ-SEAL-022)
        for n in range(1, 26):
            leaves = [hashlib.sha256(f"prop-leaf-{n}-{i}".encode("utf-8")).hexdigest() for i in range(n)]
            tree = MerkleTree.from_leaves(leaves)
            for idx in range(n):
                proof = tree.inclusion_proof(idx)
                self.assertTrue(verify_inclusion_proof(leaves[idx], idx, n, proof, tree.root))

    def test_hashchain_single_event_mutation_always_detected(self):
        # Any mutation to any event payload changes head and fails verification (REQ-SEAL-021)
        rng = random.Random(909)
        commitment = "c" * 64
        for trial in range(20):
            hb = HashChainBuilder(truth_commitment=commitment, episode_id=f"ep-prop-{trial}")
            hb.append(event_type="reset", action_payload={"seed_idx": trial}, response_payload={"ok": True}, logical_step=0)
            k = rng.randint(1, 6)
            for step in range(1, k + 1):
                hb.append(
                    event_type="tool_call",
                    action_payload={"step": step, "v": rng.randint(0, 10000)},
                    response_payload={"ok": True, "rem": 100 - step},
                    logical_step=step,
                )
            events = [e.to_dict() for e in hb.events]
            head = hb.head
            self.assertTrue(verify_hash_chain(commitment, f"ep-prop-{trial}", events, expected_head=head).valid)
            target_idx = rng.randrange(len(events))
            mut_events = [dict(e) for e in events]
            orig_d = mut_events[target_idx]["response_digest"]
            mut_events[target_idx]["response_digest"] = ("0" if orig_d[0] != "0" else "1") + orig_d[1:]
            self.assertFalse(verify_hash_chain(commitment, f"ep-prop-{trial}", mut_events, expected_head=head).valid)

    def test_unicode_nfc_and_skeleton_idempotence_property(self):
        # REQ-NLP-005: deterministic Unicode property loop across Cyrillic, Kazakh, and Latin
        import unicodedata
        from nlp import normalize_accounting_text, normalize_nfc, transliterate_to_ascii_skeleton

        samples = [
            'ТОО «Алтын Орда» #1',
            '«Жетісу Агро» ЖШС — төлем тапсырмасы',
            'Caspian Steppe LLP\u200b (Invoice #42)',
            'Тәңірі Логистика АҚ / ҚҚС-сыз',
        ]
        for s in samples:
            for form in ("NFC", "NFD", "NFKC", "NFKD"):
                variant = unicodedata.normalize(form, s)
                once = normalize_nfc(variant)
                twice = normalize_nfc(once)
                self.assertEqual(once, twice)
                norm1 = normalize_accounting_text(variant)
                norm2 = normalize_accounting_text(norm1)
                self.assertEqual(norm1, norm2)
                skel = transliterate_to_ascii_skeleton(variant)
                self.assertTrue(skel.isascii())

    def test_text_similarity_and_ngrams_unicode_stability_property(self):
        # REQ-NLP-005: candidate-matching text transforms are Unicode-form invariant
        import unicodedata
        from nlp import char_ngrams, text_similarity_bps

        pairs = [
            ('ТОО «Алтын Орда» #1', 'Altyn Orda LLP #1'),
            ('«Жетісу Агро» ЖШС', 'Zhetysu Agro LLP'),
            ('Тәңірі Логистика АҚ', 'Tengri Logistika LLP'),
            ('Сарыарка Тех ЖШС', 'Saryarka Tech LLP'),
        ]
        for a, b in pairs:
            base = text_similarity_bps(a, b)
            base_ngrams = char_ngrams(a, 3)
            for form in ("NFC", "NFD", "NFKC", "NFKD"):
                va = unicodedata.normalize(form, a)
                vb = unicodedata.normalize(form, b)
                self.assertEqual(text_similarity_bps(va, vb), base)
                self.assertEqual(char_ngrams(va, 3), base_ngrams)
            self.assertEqual(text_similarity_bps(a, b), text_similarity_bps(b, a))

    def test_money_conversion_preserves_accuracy_and_rounding(self):
        # §20.2: money conversion preserves accuracy/rounding; int minor units,
        # Decimal-from-string rates only, no float. Deterministic loop over
        # currencies, amounts, rates, and rounding modes (REQ-MONEY-001..006).
        from fractions import Fraction

        from core.money import convert_minor

        rng = random.Random(202501)
        cases = [
            (10000, "KZT", "KZT", "1", "half_even"),
            (250, "KWD", "JPY", "10", "half_even"),
            (123456, "USD", "EUR", "0.92", "half_up"),
            (999, "JPY", "KZT", "4.5", "half_even"),
            (5000, "EUR", "USD", "1.08", "half_even"),
        ]
        for _ in range(30):
            amt = rng.randint(1, 10**6)
            src, dst = rng.choice([("KZT", "USD"), ("USD", "KZT"), ("EUR", "KZT"), ("KZT", "EUR")])
            rate = rng.choice(["0.5", "1.25", "2", "0.92", "1.08"])
            mode = rng.choice(["half_even", "half_up"])
            cases.append((amt, src, dst, rate, mode))
        for amt, src, dst, rate, mode in cases:
            r1 = convert_minor(amt, src, dst, rate, mode)
            r2 = convert_minor(amt, src, dst, rate, mode)
            self.assertEqual(r1.amount_minor, r2.amount_minor, "FX conversion must be deterministic")
            self.assertIsInstance(r1.amount_minor, int)
            # Unrounded value must be exact rational; rounding error < 1 minor.
            unrounded = Fraction(str(r1.unrounded_minor))
            self.assertLessEqual(abs(Fraction(r1.amount_minor) - unrounded), Fraction(1))

    def test_je_balance_preserved_after_clean_events(self):
        # §20.2: JE balance (INV-01) preserved after each clean event.
        from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin, verify_clean_invariants
        from invariants.checks import check as invariant_check

        for seed in (11, 22, 33):
            twin = generate_clean_twin(CleanTwinSpec(episode_id=f"ep_prop_{seed}", master_seed=seed, episode_index=1))
            self.assertEqual(verify_clean_invariants(twin), [])
            for je in twin.journal_entries:
                debs = [ln["functional_debit_minor"] for ln in je["lines"]]
                creds = [ln["functional_credit_minor"] for ln in je["lines"]]
                self.assertIsNone(
                    invariant_check("INV-01", je["je_id"], {"debits": debs, "credits": creds, "currency": "KZT"}),
                    f"INV-01 must hold for clean JE {je['je_id']}",
                )

    def test_duplicate_mutation_creates_expected_diff(self):
        # §20.2: duplicate mutation creates expected diff (non-empty, truth-linked).
        from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin
        from gen.core.rng import scoped_rng
        from gen.errors.operators import inject_duplicate_payment
        from gen.truth import compute_structural_diff

        spec = CleanTwinSpec(episode_id="ep_prop_dup", master_seed=4242, episode_index=2)
        clean = generate_clean_twin(spec)
        mutated = clean.clone()
        rng = scoped_rng(spec.master_seed, "operators", spec.episode_id, 1)
        outcome = inject_duplicate_payment(mutated, rng, truth_index=1)
        diff = compute_structural_diff(clean, mutated)
        self.assertTrue(diff, "duplicate mutation must produce non-empty diff")
        self.assertEqual(outcome.truth_finding["type"], "DUPLICATE_PAYMENT")
        self.assertTrue(outcome.truth_finding["affected_ids"])

    def test_invalid_allocation_violates_specific_invariant(self):
        # §20.2: invalid allocation violates specific invariant (INV-15).
        from invariants.checks import check as invariant_check

        valid = {"allocations": [600, 400], "payment": 1000, "allow_advances": False, "currency": "KZT"}
        self.assertIsNone(invariant_check("INV-15", "PAY:1", valid))
        over = {"allocations": [700, 400], "payment": 1000, "allow_advances": False, "currency": "KZT"}
        sig = invariant_check("INV-15", "PAY:1", over)
        self.assertIsNotNone(sig, "over-allocation must violate INV-15")
        self.assertEqual(sig.invariant_id, "INV-15")

    def test_fx_policy_deterministic_for_same_snapshot(self):
        # §20.2: FX policy gives same rate for same snapshot (deterministic).
        from datetime import date

        from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin, select_permitted_fx

        twin = generate_clean_twin(CleanTwinSpec(episode_id="ep_prop_fx", master_seed=5555, episode_index=3))
        policy = twin.policy
        fx_rates = twin.fx_rates
        # Pick a foreign currency present in the twin, else skip gracefully.
        foreign = next((r["pair"].split("/")[0] for r in fx_rates if "/" in r.get("pair", "")), None)
        if foreign is None:
            self.skipTest("no FX rates in generated twin")
        target = date.fromisoformat(fx_rates[0]["effective_date"])
        first = select_permitted_fx(fx_rates, foreign, "KZT", target, policy)
        second = select_permitted_fx(fx_rates, foreign, "KZT", target, policy)
        self.assertEqual(first, second, "FX selection must be deterministic for same snapshot")

    def test_cutoff_accounts_for_timezone(self):
        # §20.2: cutoff accounts for timezone; same instant, different company
        # timezone -> different fiscal period; same timezone -> deterministic.
        from core.time_rules import fiscal_period

        policy = {"cutoff_policy": {"timezone_source": "company", "recognition_event": "service_date"}}
        events = {"service_date": "2025-03-31T23:00:00Z"}
        tokyo = {"timezone": "Asia/Tokyo", "fiscal_period_rule": "quarterly", "fiscal_year_start": "2024-04-01"}
        utc = {"timezone": "UTC", "fiscal_period_rule": "quarterly", "fiscal_year_start": "2024-04-01"}
        self.assertEqual(fiscal_period(events, policy, tokyo), fiscal_period(events, policy, tokyo))
        self.assertNotEqual(
            fiscal_period(events, policy, tokyo),
            fiscal_period(events, policy, utc),
            "timezone must affect cutoff period",
        )

    def test_scoring_stays_in_unit_interval(self):
        # §20.2: F1 stays in [0,1]; the official reward is clip([-1,1]) and is
        # covered by tests/official/test_block3_scorer.py. Since D-18-01 the
        # reward path of scoring/reward.py IS the official one, so the bound
        # asserted below is [-1, 1] -- not the superseded provisional [0, 1].
        from fractions import Fraction

        from scoring.reward import compute_reward, f1_score

        rng = random.Random(777)
        for _ in range(40):
            tp = rng.randint(0, 5)
            fp = rng.randint(0, 5)
            fn = rng.randint(0, 5)
            f1 = f1_score(tp, fp, fn)
            self.assertGreaterEqual(f1, Fraction(0))
            self.assertLessEqual(f1, Fraction(1))
        # Reward bounds over representative submissions.
        # Official formula: return = clip([-1, 1], 2*F1 - 1 - 0.2*steps/100),
        # so the bound is [-1, 1] and a missed error may score negative
        # (official test 2). The former assertion floor of 0 was the
        # superseded provisional formula (BUG-TL-0001).
        from tests.scoring.fixtures import duplicate_payment_truth, honest_finding

        truth = duplicate_payment_truth("T-PROP-BOUNDS")
        honest = honest_finding(truth)
        for findings, steps in (([], 0), ([honest], 0), ([honest], 100), ([honest, honest], 50)):
            r = compute_reward(findings, [truth], steps)
            self.assertGreaterEqual(r.reward, Fraction(-1))
            self.assertLessEqual(r.reward, Fraction(1))
        self.assertEqual(compute_reward([], [truth], 100).reward, Fraction(-1))

    def test_duplicate_prediction_never_increases_tp(self):
        # §20.2: duplicating a prediction must not increase TP.
        from scoring.matcher import optimal_matching
        from tests.scoring.fixtures import duplicate_payment_truth, honest_finding

        truth = duplicate_payment_truth("T-PROP-DUP")
        honest = honest_finding(truth)
        single = optimal_matching([honest], [truth])
        triple = optimal_matching([honest, honest, honest], [truth])
        self.assertEqual(single.tp, 1)
        self.assertEqual(triple.tp, 1, "duplicate findings must not inflate TP")
        self.assertEqual(triple.fp, 2)

    def test_explanation_never_changes_base_reward_property(self):
        # TZ §20.2: arbitrary free-text explanation changes leave official reward 100% invariant
        from contracts.models import Finding, TruthFinding
        from scoring.reward import compute_reward

        truth = TruthFinding.from_dict(
            {
                "schema_version": "1.0.0",
                "truth_id": "T-PROP-01",
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
        explanations = [
            None,
            "",
            "x",
            "Оплата дублирована по счету INV:10 на 250.00 KZT",
            "Қайталанған төлем PAY:20 (25000 тиын)",
            "Long detailed explanation " * 15,
        ]
        ref_reward = None
        for exp in explanations:
            kw = dict(
                type="DUPLICATE_PAYMENT",
                affected_ids=("INV:10", "PAY:20"),
                claimed_amount=25000,
                currency="KZT",
                evidence_ids=("INV:10", "PAY:20"),
            )
            if exp is not None:
                kw["explanation"] = exp
            r = compute_reward([Finding(**kw)], [truth], 12).reward
            if ref_reward is None:
                ref_reward = r
            else:
                self.assertEqual(r, ref_reward)


try:
    import hypothesis  # noqa: F401
    from hypothesis import given, settings, strategies as st

    _HYPOTHESIS_AVAILABLE = True
except ImportError:
    _HYPOTHESIS_AVAILABLE = False


if _HYPOTHESIS_AVAILABLE:
    class TestHypothesisProperties(unittest.TestCase):
        """Optional Hypothesis property tests (TZ §20.2, task 13.5).

        Run only when ``hypothesis`` is installed (dev extra). Core never requires
        it (REQ-UNIQUE-003). When absent, these tests are SKIPPED, not failed.
        """

        @settings(max_examples=30, deadline=None)
        @given(st.dictionaries(st.text(min_size=1, max_size=6), st.integers(min_value=0, max_value=1000), min_size=1, max_size=5))
        def test_canonical_stable_under_hypothesis_permutation(self, payload) -> None:
            import random as _random

            keys = list(payload.keys())
            _random.Random(0).shuffle(keys)
            permuted = {k: payload[k] for k in keys}
            self.assertEqual(canonical_json(payload), canonical_json(permuted))

        @settings(max_examples=30, deadline=None)
        @given(st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=5))
        def test_f1_in_unit_interval_hypothesis(self, tp, fp, fn) -> None:
            from fractions import Fraction

            from scoring.reward import f1_score

            f1 = f1_score(tp, fp, fn)
            self.assertGreaterEqual(f1, Fraction(0))
            self.assertLessEqual(f1, Fraction(1))

else:
    @unittest.skip("hypothesis extra not installed")
    class TestHypothesisProperties(unittest.TestCase):
        def test_optional_dependency(self):
            pass


if __name__ == "__main__":
    unittest.main()
