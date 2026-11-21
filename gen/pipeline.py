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

            ep_dir = Path(out_root) / recipe.twin_spec.episode_id
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
    raise ValueError(f"unknown split: {split!r}")


__all__ = [
    "EpisodeRecipe",
    "GeneratedEpisode",
    "build_episode",
    "default_dataset_recipes",
]
