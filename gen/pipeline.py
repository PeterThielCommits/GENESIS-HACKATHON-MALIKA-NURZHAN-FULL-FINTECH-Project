"""End-to-end episode generation pipeline (Phase 3 + Phase 4 + Phase 7).

Builds deterministic clean and mutated episodes with structural-diff truth,
rejection sampling, and manifest sealing — strictly inside ``gen/`` without
importing ``verifier``, ``scoring``, or ``seal``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from contracts.canonical import sha256_hex as canonical_sha256
from gen.core.clean_twin import (
    CleanTwin,
    CleanTwinSpec,
    generate_clean_twin,
    verify_clean_invariants,
)
from gen.core.rng import derive_bytes, scoped_rng
from gen.errors.operators import (
    OperatorOutcome,
    inject_duplicate_payment,
    inject_fx_mismatch,
    inject_partial_allocation,
    inject_period_cutoff,
)
from gen.serialize import verify_episode_manifest, write_episode
from gen.truth import compute_structural_diff, validate_truth_list


@dataclass(frozen=True)
class EpisodeRecipe:
    """Declarative recipe for one generated TwinLedger episode."""

    twin_spec: CleanTwinSpec
    anomalies: tuple[str, ...] = ()  # e.g. ("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH")
    partial_subcase: str = "premature_paid"


@dataclass(frozen=True)
class GeneratedEpisode:
    """In-memory + on-disk result of building one episode."""

    episode_id: str
    episode_dir: Path
    manifest: dict[str, Any]
    truths: tuple[dict[str, Any], ...]
    structural_diff: dict[str, Any]
    attempts: int


def build_episode(
    recipe: EpisodeRecipe,
    out_root: Path | str,
    *,
    max_attempts: int = 20,
    out_dir_exact: bool = False,
) -> GeneratedEpisode:
    """Generate, validate, and serialize one episode with rejection sampling."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    cfg_hash = canonical_sha256(
        {
            "episode_id": recipe.twin_spec.episode_id,
            "master_seed": recipe.twin_spec.master_seed,
            "episode_index": recipe.twin_spec.episode_index,
            "functional_currency": recipe.twin_spec.functional_currency,
            "foreign_currencies": list(recipe.twin_spec.foreign_currencies),
            "timezone": recipe.twin_spec.timezone,
            "fiscal_period_rule": recipe.twin_spec.fiscal_period_rule,
            "rounding_mode": recipe.twin_spec.rounding_mode,
            "rate_date_rule": recipe.twin_spec.rate_date_rule,
            "fallback_rule": recipe.twin_spec.fallback_rule,
            "quote_convention": recipe.twin_spec.quote_convention,
            "recognition_event": recipe.twin_spec.recognition_event,
            "id_style": recipe.twin_spec.id_style,
            "distractor_classes": list(recipe.twin_spec.distractor_classes),
        }
    )

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            clean: CleanTwin = generate_clean_twin(recipe.twin_spec)
            mutated: CleanTwin = clean.clone()
            op_rng = scoped_rng(
                recipe.twin_spec.master_seed,
                "operators",
                recipe.twin_spec.episode_id,
                attempt,
            )

            outcomes: list[OperatorOutcome] = []
            used_invs: set[str] = set()
            used_jes: set[str] = set()

            for t_idx, atype in enumerate(recipe.anomalies, start=1):
                if atype == "DUPLICATE_PAYMENT":
                    oc = inject_duplicate_payment(mutated, op_rng, truth_index=t_idx, excluded_inv_ids=used_invs)
                    used_invs.add(oc.provenance["target_invoice"])
                elif atype == "PARTIAL_PAYMENT_ALLOCATION":
                    oc = inject_partial_allocation(
                        mutated,
                        op_rng,
                        truth_index=t_idx,
                        subcase=recipe.partial_subcase,
                        excluded_inv_ids=used_invs,
                    )
                    used_invs.add(oc.provenance["target_invoice"])
                elif atype == "FX_RATE_MISMATCH":
                    oc = inject_fx_mismatch(mutated, op_rng, truth_index=t_idx, excluded_je_ids=used_jes)
                    used_jes.add(oc.provenance["je_id"])
                elif atype == "PERIOD_CUTOFF":
                    oc = inject_period_cutoff(mutated, op_rng, truth_index=t_idx, excluded_je_ids=used_jes)
                    used_jes.add(oc.provenance["je_id"])
                else:
                    raise ValueError(f"unsupported anomaly type in recipe: {atype!r}")
                outcomes.append(oc)

            # Structural integrity check after mutation (INV-01 balance & unique PKs still hold)
            inv_errs = verify_clean_invariants(mutated)
            if inv_errs:
                raise RuntimeError(f"mutated book violated structural invariants: {inv_errs}")

            truths = [oc.truth_finding for oc in outcomes]
            t_errs = validate_truth_list(truths)
            if t_errs:
                raise RuntimeError(f"truth list invalid: {t_errs}")

            diff = compute_structural_diff(clean, mutated)
            if recipe.anomalies and not diff:
                raise RuntimeError("mutated episode had empty structural diff")
            if not recipe.anomalies and diff:
                raise RuntimeError("clean episode had non-empty structural diff")

            salt_hex = derive_bytes(
                recipe.twin_spec.master_seed,
                "truth_salt",
                recipe.twin_spec.episode_id,
                attempt,
                length=32,
            ).hex()

            ep_dir = Path(out_root) if out_dir_exact else (Path(out_root) / recipe.twin_spec.episode_id)
            manifest = write_episode(
                ep_dir,
                mutated,
                truths,
                config_hash=cfg_hash,
                commitment_salt_hex=salt_hex,
                provenance={
                    "master_seed": recipe.twin_spec.master_seed,
                    "episode_index": recipe.twin_spec.episode_index,
                    "attempt": attempt,
                    "operators": [
                        {"operator": oc.operator_name, "mutated_ids": list(oc.mutated_ids), **oc.provenance}
                        for oc in outcomes
                    ],
                    "structural_diff": diff,
                },
            )
            m_errs = verify_episode_manifest(ep_dir)
            if m_errs:
                raise RuntimeError(f"manifest verification failed: {m_errs}")

            return GeneratedEpisode(
                episode_id=recipe.twin_spec.episode_id,
                episode_dir=ep_dir,
                manifest=manifest,
                truths=tuple(truths),
                structural_diff=diff,
                attempts=attempt,
            )
        except (ValueError, RuntimeError) as exc:
            last_err = exc
            continue

    raise RuntimeError(
        f"rejection sampling exhausted {max_attempts} attempts for {recipe.twin_spec.episode_id}: {last_err}"
    )


def default_dataset_recipes(split: str, master_seed: int = 2025) -> list[EpisodeRecipe]:
    """Deterministic benchmark recipes covering clean, single-type, compound, and distractor-rich books."""
    if split == "dev":
        return [
            # 1. Clean book with rich distractors across all 4 families
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_001_clean_distractors",
                    master_seed=master_seed,
                    episode_index=1,
                    id_style="A",
                    distractor_classes=(
                        "D-DUP-01", "D-DUP-02", "D-DUP-03", "D-DUP-04",
                        "D-PART-01", "D-PART-03", "D-PART-04",
                        "D-FX-01", "D-FX-02",
                        "D-CUT-01", "D-CUT-02", "D-CUT-03", "D-CUT-04",
                    ),
                ),
                anomalies=(),
            ),
            # 2. Single DUPLICATE_PAYMENT + distractors (ID family B)
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_002_duplicate",
                    master_seed=master_seed,
                    episode_index=2,
                    id_style="B",
                    distractor_classes=("D-DUP-02", "D-DUP-04", "D-PART-01"),
                ),
                anomalies=("DUPLICATE_PAYMENT",),
            ),
            # 3. Single PARTIAL_PAYMENT_ALLOCATION (premature paid) + distractors (ID family C)
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_003_partial",
                    master_seed=master_seed,
                    episode_index=3,
                    id_style="C",
                    allow_advances=True,
                    distractor_classes=("D-PART-01", "D-PART-02", "D-PART-04"),
                ),
                anomalies=("PARTIAL_PAYMENT_ALLOCATION",),
                partial_subcase="premature_paid",
            ),
            # 4. Single FX_RATE_MISMATCH (inverse quote + half_up + KWD/JPY) (ID family D)
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_004_fx_inverse",
                    master_seed=master_seed,
                    episode_index=4,
                    functional_currency="KWD",
                    foreign_currencies=("USD", "JPY"),
                    rounding_mode="half_up",
                    quote_convention="foreign_per_functional",
                    id_style="D",
                    distractor_classes=("D-FX-01", "D-FX-02"),
                ),
                anomalies=("FX_RATE_MISMATCH",),
            ),
            # 5. Single PERIOD_CUTOFF (quarterly fiscal calendar + distractors)
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_005_cutoff_quarterly",
                    master_seed=master_seed,
                    episode_index=5,
                    fiscal_period_rule="quarterly",
                    id_style="A",
                    distractor_classes=("D-CUT-01", "D-CUT-02", "D-CUT-04"),
                ),
                anomalies=("PERIOD_CUTOFF",),
            ),
            # 6. Compound all-4-types + distractors
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_dev_006_compound_all4",
                    master_seed=master_seed,
                    episode_index=6,
                    num_domestic_invoices=10,
                    num_foreign_invoices=6,
                    id_style="A",
                    distractor_classes=("D-DUP-01", "D-PART-03", "D-FX-01", "D-CUT-02"),
                ),
                anomalies=(
                    "DUPLICATE_PAYMENT",
                    "PARTIAL_PAYMENT_ALLOCATION",
                    "FX_RATE_MISMATCH",
                    "PERIOD_CUTOFF",
                ),
                partial_subcase="over_allocated_payment",
            ),
        ]
    if split == "train":
        return [
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_train_001_clean",
                    master_seed=master_seed + 100,
                    episode_index=1,
                    id_style="B",
                    distractor_classes=("D-DUP-02", "D-PART-01", "D-FX-01", "D-CUT-01"),
                ),
                anomalies=(),
            ),
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_train_002_dup_fx",
                    master_seed=master_seed + 100,
                    episode_index=2,
                    functional_currency="USD",
                    foreign_currencies=("EUR", "JPY"),
                    timezone="UTC",
                    id_style="C",
                    distractor_classes=("D-DUP-04", "D-FX-02"),
                ),
                anomalies=("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH"),
            ),
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_train_003_part_cutoff",
                    master_seed=master_seed + 100,
                    episode_index=3,
                    id_style="D",
                    distractor_classes=("D-PART-04", "D-CUT-04"),
                ),
                anomalies=("PARTIAL_PAYMENT_ALLOCATION", "PERIOD_CUTOFF"),
                partial_subcase="premature_paid",
            ),
            EpisodeRecipe(
                twin_spec=CleanTwinSpec(
                    episode_id="ep_train_004_compound_all4",
                    master_seed=master_seed + 100,
                    episode_index=4,
                    num_domestic_invoices=10,
                    num_foreign_invoices=6,
                    id_style="A",
                    distractor_classes=("D-DUP-03", "D-PART-03", "D-FX-01", "D-CUT-03"),
                ),
                anomalies=(
                    "DUPLICATE_PAYMENT",
                    "PARTIAL_PAYMENT_ALLOCATION",
                    "FX_RATE_MISMATCH",
                    "PERIOD_CUTOFF",
                ),
            ),
        ]
    if split == "official_d20":
        return official_d20_recipes(master_seed=master_seed)
    raise ValueError(f"unknown split: {split!r}")


def official_d20_recipes(master_seed: int = 2026) -> list[EpisodeRecipe]:
    """Full 20-episode closed evaluation matrix D01..D20 (Genesis FinTech 2026-11-20).

    Scenario coverage:
      - D01..D05: 5 clean companies (normal, split payment, refund/CN, recurring amounts, FX/cutoff boundary)
      - D06..D08: 3 duplicate payment scenarios with varying IDs/currencies/distractors
      - D09..D11: 3 missing/partial payment allocation scenarios (missing_allocation, premature_paid, over_allocated_payment)
      - D12..D13: 2 FX rate/date/quote-convention mismatch scenarios
      - D14..D15: 2 period cutoff scenarios (different timezones & fiscal calendars)
      - D16..D18: 3 variants of Interaction Scenario #1 (FX_PERIOD_INTERACTION: FX_RATE_MISMATCH + PERIOD_CUTOFF)
      - D19..D20: 2 variants of Interaction Scenario #2 (PAYMENT_ALLOCATION_INTERACTION: DUPLICATE_PAYMENT + PARTIAL_PAYMENT_ALLOCATION)
    """
    return [
        # D01-D05: Clean books
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D01_clean_standard",
                master_seed=master_seed,
                episode_index=101,
                functional_currency="KZT",
                foreign_currencies=("USD", "EUR"),
                timezone="Asia/Almaty",
                id_style="A",
                distractor_classes=(),
            ),
            anomalies=(),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D02_clean_split_payment",
                master_seed=master_seed,
                episode_index=102,
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                allow_multi_invoice_split=True,
                id_style="B",
                distractor_classes=("D-PART-01", "D-PART-03"),
            ),
            anomalies=(),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D03_clean_refund_credit_note",
                master_seed=master_seed,
                episode_index=103,
                functional_currency="USD",
                foreign_currencies=("EUR",),
                timezone="UTC",
                id_style="C",
                distractor_classes=("D-DUP-01", "D-DUP-04", "D-PART-04"),
            ),
            anomalies=(),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D04_clean_recurring_amounts",
                master_seed=master_seed,
                episode_index=104,
                functional_currency="EUR",
                foreign_currencies=("USD",),
                timezone="Europe/Berlin",
                id_style="D",
                distractor_classes=("D-DUP-02", "D-DUP-03"),
            ),
            anomalies=(),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D05_clean_fx_cutoff_boundary",
                master_seed=master_seed,
                episode_index=105,
                functional_currency="KZT",
                foreign_currencies=("USD", "EUR"),
                timezone="Asia/Almaty",
                id_style="A",
                distractor_classes=("D-FX-01", "D-FX-02", "D-CUT-01", "D-CUT-02", "D-CUT-04"),
            ),
            anomalies=(),
        ),
        # D06-D08: Duplicate payments (with clean recurring distractors that must NOT fire)
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D06_duplicate_kzt_recurring",
                master_seed=master_seed,
                episode_index=106,
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                id_style="A",
                distractor_classes=("D-DUP-02", "D-DUP-03"),
            ),
            anomalies=("DUPLICATE_PAYMENT",),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D07_duplicate_usd_refund",
                master_seed=master_seed,
                episode_index=107,
                functional_currency="USD",
                foreign_currencies=("EUR",),
                timezone="UTC",
                id_style="B",
                distractor_classes=("D-DUP-02", "D-DUP-04"),
            ),
            anomalies=("DUPLICATE_PAYMENT",),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D08_duplicate_eur_cn",
                master_seed=master_seed,
                episode_index=108,
                functional_currency="EUR",
                foreign_currencies=("USD",),
                timezone="Europe/Berlin",
                id_style="C",
                distractor_classes=("D-DUP-01", "D-DUP-03"),
            ),
            anomalies=("DUPLICATE_PAYMENT",),
        ),
        # D09-D11: Missing & partial payment allocation
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D09_missing_allocation",
                master_seed=master_seed,
                episode_index=109,
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                allow_advances=False,
                id_style="A",
                distractor_classes=("D-PART-01", "D-PART-03"),
            ),
            anomalies=("PARTIAL_PAYMENT_ALLOCATION",),
            partial_subcase="missing_allocation",
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D10_partial_premature_paid",
                master_seed=master_seed,
                episode_index=110,
                functional_currency="USD",
                foreign_currencies=("EUR",),
                timezone="UTC",
                allow_advances=True,
                id_style="B",
                distractor_classes=("D-PART-01", "D-PART-02", "D-PART-04"),
            ),
            anomalies=("PARTIAL_PAYMENT_ALLOCATION",),
            partial_subcase="premature_paid",
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D11_partial_over_allocated",
                master_seed=master_seed,
                episode_index=111,
                functional_currency="EUR",
                foreign_currencies=("USD",),
                timezone="Europe/Berlin",
                id_style="C",
                distractor_classes=("D-PART-03", "D-PART-04"),
            ),
            anomalies=("PARTIAL_PAYMENT_ALLOCATION",),
            partial_subcase="over_allocated_payment",
        ),
        # D12-D13: FX conversion mismatches
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D12_fx_direct_document_date",
                master_seed=master_seed,
                episode_index=112,
                functional_currency="KZT",
                foreign_currencies=("USD", "EUR"),
                rounding_mode="half_even",
                rate_date_rule="document_date",
                quote_convention="functional_per_foreign",
                timezone="Asia/Almaty",
                id_style="A",
                distractor_classes=("D-FX-01", "D-FX-02"),
            ),
            anomalies=("FX_RATE_MISMATCH",),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D13_fx_inverse_operation_date",
                master_seed=master_seed,
                episode_index=113,
                functional_currency="KWD",
                foreign_currencies=("USD", "JPY"),
                rounding_mode="half_up",
                rate_date_rule="operation_date",
                quote_convention="foreign_per_functional",
                timezone="UTC",
                id_style="D",
                distractor_classes=("D-FX-01",),
            ),
            anomalies=("FX_RATE_MISMATCH",),
        ),
        # D14-D15: Period cutoff errors
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D14_cutoff_almaty_monthly",
                master_seed=master_seed,
                episode_index=114,
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                fiscal_period_rule="monthly",
                id_style="B",
                distractor_classes=("D-CUT-01", "D-CUT-02", "D-CUT-04"),
            ),
            anomalies=("PERIOD_CUTOFF",),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D15_cutoff_utc_quarterly",
                master_seed=master_seed,
                episode_index=115,
                functional_currency="USD",
                foreign_currencies=("EUR",),
                timezone="UTC",
                fiscal_period_rule="quarterly",
                id_style="C",
                distractor_classes=("D-CUT-02", "D-CUT-04"),
            ),
            anomalies=("PERIOD_CUTOFF",),
        ),
        # D16-D18: Interaction Scenario #1 — FX_PERIOD_INTERACTION (FX_RATE_MISMATCH + PERIOD_CUTOFF)
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D16_interaction1_fx_cutoff_kzt",
                master_seed=master_seed,
                episode_index=116,
                functional_currency="KZT",
                foreign_currencies=("USD", "EUR"),
                timezone="Asia/Almaty",
                fiscal_period_rule="monthly",
                rounding_mode="half_even",
                quote_convention="functional_per_foreign",
                id_style="A",
                num_domestic_invoices=10,
                num_foreign_invoices=6,
                distractor_classes=("D-FX-01", "D-CUT-01", "D-CUT-02"),
            ),
            anomalies=("FX_RATE_MISMATCH", "PERIOD_CUTOFF"),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D17_interaction1_fx_cutoff_kwd_qtr",
                master_seed=master_seed,
                episode_index=117,
                functional_currency="KWD",
                foreign_currencies=("USD", "JPY"),
                timezone="UTC",
                fiscal_period_rule="quarterly",
                rounding_mode="half_up",
                quote_convention="foreign_per_functional",
                id_style="D",
                num_domestic_invoices=10,
                num_foreign_invoices=6,
                distractor_classes=("D-FX-01", "D-CUT-04"),
            ),
            anomalies=("FX_RATE_MISMATCH", "PERIOD_CUTOFF"),
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D18_interaction1_fx_cutoff_eur",
                master_seed=master_seed,
                episode_index=118,
                functional_currency="EUR",
                foreign_currencies=("USD", "JPY"),
                timezone="Europe/Berlin",
                fiscal_period_rule="monthly",
                rounding_mode="half_even",
                rate_date_rule="operation_date",
                quote_convention="functional_per_foreign",
                id_style="B",
                num_domestic_invoices=10,
                num_foreign_invoices=6,
                distractor_classes=("D-FX-01", "D-CUT-02", "D-CUT-04"),
            ),
            anomalies=("FX_RATE_MISMATCH", "PERIOD_CUTOFF"),
        ),
        # D19-D20: Interaction Scenario #2 — PAYMENT_ALLOCATION_INTERACTION (DUPLICATE_PAYMENT + PARTIAL_PAYMENT_ALLOCATION)
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D19_interaction2_dup_missing_alloc",
                master_seed=master_seed,
                episode_index=119,
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                allow_advances=False,
                id_style="A",
                num_domestic_invoices=10,
                num_foreign_invoices=4,
                distractor_classes=("D-DUP-02", "D-DUP-04", "D-PART-01", "D-PART-03"),
            ),
            anomalies=("DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION"),
            partial_subcase="missing_allocation",
        ),
        EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id="D20_interaction2_dup_premature_paid",
                master_seed=master_seed,
                episode_index=120,
                functional_currency="USD",
                foreign_currencies=("EUR",),
                timezone="UTC",
                allow_advances=True,
                id_style="C",
                num_domestic_invoices=10,
                num_foreign_invoices=4,
                distractor_classes=("D-DUP-01", "D-DUP-03", "D-PART-02", "D-PART-04"),
            ),
            anomalies=("DUPLICATE_PAYMENT", "PARTIAL_PAYMENT_ALLOCATION"),
            partial_subcase="premature_paid",
        ),
    ]


_D20_BY_CODE: dict[str, int] = {f"D{i:02d}": i - 1 for i in range(1, 21)}


def recipe_from_config(seed: int, config: dict[str, Any] | None = None) -> EpisodeRecipe:
    """Build a deterministic ``EpisodeRecipe`` from ``(seed, config)``.

    Supports named official scenarios (``D01``..``D20``, ``C``, ``E``, ``L``,
    ``clean``, ``duplicate``, ``partial``, ``missing_allocation``, ``fx``,
    ``cutoff``, ``interaction_1``, ``interaction_2``) as well as fine-grained
    overrides of any ``CleanTwinSpec`` field and ``anomalies`` list.
    """
    cfg = dict(config or {})
    scenario = str(cfg.get("scenario", "")).strip()
    scenario_upper = scenario.upper()

    # Start from a preset if named
    base: EpisodeRecipe | None = None
    if scenario_upper in _D20_BY_CODE:
        base = official_d20_recipes(master_seed=seed)[_D20_BY_CODE[scenario_upper]]
    elif scenario_upper == "C" or scenario.lower() == "clean":
        base = official_d20_recipes(master_seed=seed)[0]
    elif scenario_upper == "E":
        base = EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id=str(cfg.get("episode_id", f"ep_E_{seed}")),
                master_seed=seed,
                episode_index=int(cfg.get("episode_index", 1)),
                functional_currency="KZT",
                foreign_currencies=("USD",),
                timezone="Asia/Almaty",
                id_style="A",
            ),
            anomalies=("DUPLICATE_PAYMENT",),
        )
    elif scenario_upper == "L" or bool(cfg.get("large", False)):
        min_rows = max(105, int(cfg.get("min_records", 105)))
        base = EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id=str(cfg.get("episode_id", f"ep_L_{seed}")),
                master_seed=seed,
                episode_index=int(cfg.get("episode_index", 2)),
                functional_currency="KZT",
                foreign_currencies=("USD", "EUR"),
                timezone="Asia/Almaty",
                id_style="A",
                company_size="L",
                num_counterparties=12,
                num_domestic_invoices=min_rows,
                num_foreign_invoices=6,
            ),
            anomalies=tuple(cfg.get("anomalies", ())),
        )
    elif scenario.lower() in ("interaction_1", "fx_period_interaction"):
        base = official_d20_recipes(master_seed=seed)[15]  # D16
    elif scenario.lower() in ("interaction_2", "payment_allocation_interaction"):
        base = official_d20_recipes(master_seed=seed)[18]  # D19

    if base is None:
        raw_anoms = cfg.get("anomalies")
        if raw_anoms is None:
            anom_map = {
                "duplicate": ("DUPLICATE_PAYMENT",),
                "duplicate_payment": ("DUPLICATE_PAYMENT",),
                "partial": ("PARTIAL_PAYMENT_ALLOCATION",),
                "partial_payment_allocation": ("PARTIAL_PAYMENT_ALLOCATION",),
                "missing_allocation": ("PARTIAL_PAYMENT_ALLOCATION",),
                "fx": ("FX_RATE_MISMATCH",),
                "fx_rate_mismatch": ("FX_RATE_MISMATCH",),
                "cutoff": ("PERIOD_CUTOFF",),
                "period_cutoff": ("PERIOD_CUTOFF",),
            }
            anomalies = anom_map.get(scenario.lower(), ())
        else:
            anomalies = tuple(str(a) for a in raw_anoms)

        subcase = str(
            cfg.get(
                "partial_subcase",
                "missing_allocation" if scenario.lower() == "missing_allocation" else "premature_paid",
            )
        )
        base = EpisodeRecipe(
            twin_spec=CleanTwinSpec(
                episode_id=str(cfg.get("episode_id", f"ep_{seed}")),
                master_seed=seed,
                episode_index=int(cfg.get("episode_index", 0)),
            ),
            anomalies=anomalies,
            partial_subcase=subcase,
        )

    ts = base.twin_spec
    min_records = int(cfg.get("min_records", 0))
    num_dom = int(cfg.get("num_domestic_invoices", ts.num_domestic_invoices))
    if min_records > 0:
        num_dom = max(num_dom, min_records)
    num_for = min(10, int(cfg.get("num_foreign_invoices", ts.num_foreign_invoices)))

    anomalies_final = (
        tuple(str(a) for a in cfg["anomalies"])
        if "anomalies" in cfg and cfg["anomalies"] is not None
        else base.anomalies
    )
    subcase_final = str(cfg.get("partial_subcase", base.partial_subcase))

    # Build final CleanTwinSpec respecting explicit overrides
    foreign_curs = (
        tuple(str(c) for c in cfg["foreign_currencies"])
        if "foreign_currencies" in cfg
        else ts.foreign_currencies
    )
    distractors = (
        tuple(str(d) for d in cfg["distractor_classes"])
        if "distractor_classes" in cfg
        else ts.distractor_classes
    )

    spec = CleanTwinSpec(
        episode_id=str(cfg.get("episode_id", ts.episode_id)),
        master_seed=seed,
        episode_index=int(cfg.get("episode_index", ts.episode_index)),
        functional_currency=str(cfg.get("functional_currency", ts.functional_currency)),
        foreign_currencies=foreign_curs,
        timezone=str(cfg.get("timezone", ts.timezone)),
        fiscal_period_rule=str(cfg.get("fiscal_period_rule", ts.fiscal_period_rule)),
        rounding_mode=str(cfg.get("rounding_mode", ts.rounding_mode)),
        rate_date_rule=str(cfg.get("rate_date_rule", ts.rate_date_rule)),
        fallback_rule=str(cfg.get("fallback_rule", ts.fallback_rule)),
        quote_convention=str(cfg.get("quote_convention", ts.quote_convention)),
        recognition_event=str(cfg.get("recognition_event", ts.recognition_event)),
        allow_advances=bool(cfg.get("allow_advances", ts.allow_advances)),
        allow_multi_invoice_split=bool(cfg.get("allow_multi_invoice_split", ts.allow_multi_invoice_split)),
        id_style=str(cfg.get("id_style", ts.id_style)),
        company_size=str(cfg.get("company_size", ts.company_size)),
        num_counterparties=int(cfg.get("num_counterparties", ts.num_counterparties)),
        num_domestic_invoices=num_dom,
        num_foreign_invoices=num_for,
        distractor_classes=distractors,
        max_steps=int(cfg.get("max_steps", ts.max_steps)),
        max_page_size=int(cfg.get("max_page_size", ts.max_page_size)),
        max_findings=int(cfg.get("max_findings", ts.max_findings)),
        max_evidence_ids=int(cfg.get("max_evidence_ids", ts.max_evidence_ids)),
    )
    return EpisodeRecipe(twin_spec=spec, anomalies=anomalies_final, partial_subcase=subcase_final)


def build_episode_from_config(
    seed: int,
    config: dict[str, Any] | None,
    output_dir: Path | str,
) -> GeneratedEpisode:
    """Generate one episode directly into ``output_dir`` from ``(seed, config)``."""
    recipe = recipe_from_config(seed, config)
    return build_episode(recipe, output_dir, out_dir_exact=True)


__all__ = [
    "EpisodeRecipe",
    "GeneratedEpisode",
    "build_episode",
    "build_episode_from_config",
    "default_dataset_recipes",
    "official_d20_recipes",
    "recipe_from_config",
]
