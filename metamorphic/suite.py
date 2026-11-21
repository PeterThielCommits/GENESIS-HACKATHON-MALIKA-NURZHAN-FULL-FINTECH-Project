#!/usr/bin/env python3
"""Metamorphic Invariance Verification Suite M-01 .. M-07 (Phase 13 — TZ §20.3).

Verifies for all 7 semantics-preserving transformations ``T`` on generated episodes:
  1. ``discover(T(E)) == T(discover(E))`` (independent public verifier invariance);
  2. ``reward(policy(T(E)), T(truth(E))) == reward(policy(E), truth(E))`` (exact
     official reward invariance under public baseline auditor).

Transformations implemented:
  - ``M-01`` ``row_permutation``: shuffle JSONL rows across public tables
  - ``M-02`` ``id_bijection``: bijective per-namespace ID renaming + inverse map
  - ``M-03`` ``entity_renaming``: rename company & counterparty names/aliases
  - ``M-04`` ``timezone_instant_representation``: rewrite ISO timestamps as
    equivalent UTC ``Z`` instants for the exact same physical moment while keeping
    ``company.timezone`` fixed (preserving accounting periods)
  - ``M-05`` ``json_key_order``: reverse object key insertion order across files
  - ``M-06`` ``equivalent_description``: rewrite prose descriptions (``en`` -> ``kk``)
    without altering structured fields
  - ``M-07`` ``jsonl_serialization_variants``: non-semantic whitespace formatting
    variants across JSON and JSONL files

Writes ``artifacts/reports/latest/metamorphic_report.json``.
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from arena.policies.catalog import run_baseline_policy
from contracts.canonical import canonical_json, sha256_hex
from contracts.models import Finding, TruthFinding
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from gen.core.clean_twin import CleanTwinSpec
from gen.pipeline import EpisodeRecipe, build_episode
from metamorphic.paired_transform import transform_episode_copy
from scoring.reward import compute_reward, render_decimal
from verifier import discover

DEFAULT_REPORT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "metamorphic_report.json"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]], *, pretty_ws: bool = False) -> None:
    sep = (", ", ": ") if pretty_ws else (",", ":")
    lines = [json.dumps(r, sort_keys=not pretty_ws, separators=sep, ensure_ascii=False) for r in rows]
    suffix = "  \n" if pretty_ws else "\n"
    path.write_text((suffix.join(lines) + suffix) if lines else "", encoding="utf-8")


def _to_utc_equivalent_ts(ts: str) -> str:
    if not isinstance(ts, str) or "T" not in ts:
        return ts
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return ts
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _reverse_dict_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _reverse_dict_keys(obj[k]) for k in reversed(list(obj.keys()))}
    if isinstance(obj, list):
        return [_reverse_dict_keys(v) for v in obj]
    return obj


def _apply_transform(
    transform_id: str,
    src_ep: Path,
    dst_ep: Path,
) -> dict[str, str]:
    """Apply transformation ``transform_id`` to ``dst_ep`` and return inverse ID map."""
    if transform_id == "M-01":
        transform_episode_copy(src_ep, dst_ep, permute_rows=True, remap_ids=False, seed=202501)
        return {}

    if transform_id == "M-02":
        res = transform_episode_copy(src_ep, dst_ep, permute_rows=False, remap_ids=True, seed=202502)
        return res.inverse_map

    if dst_ep.exists():
        shutil.rmtree(dst_ep)
    shutil.copytree(src_ep, dst_ep)
    pub = dst_ep / "public"

    if transform_id == "M-03":  # entity_renaming
        comp_path = pub / "company.json"
        comp = json.loads(comp_path.read_text(encoding="utf-8"))
        comp["legal_name"] = "Renamed Metamorphic Holdings ЖШС"
        comp["name_variants"] = {
            "en": "Renamed Metamorphic Holdings LLP",
            "ru": "ТОО «Переименованный Холдинг»",
            "kk": "«Атауы Өзгертілген Холдинг» ЖШС",
        }
        comp_path.write_text(canonical_json(comp) + "\n", encoding="utf-8")

        cps = _read_jsonl(pub / "counterparties.jsonl")
        for idx, cp in enumerate(cps):
            cp["name"] = f"ЖШС Контрагент Метаморф #{idx + 1}"
            cp["aliases"] = [f"Metamorphic Counterparty #{idx + 1} LLP"]
        _write_jsonl(pub / "counterparties.jsonl", cps)
        return {}

    if transform_id == "M-04":  # timezone_instant_representation (same physical instant in +00:00)
        for fname, ts_fields in (
            ("fx_rates.jsonl", ("publication_timestamp",)),
            ("invoices.jsonl", ("issue_timestamp", "service_start", "service_end", "due_timestamp")),
            ("payments.jsonl", ("timestamp",)),
            ("credit_notes.jsonl", ("timestamp",)),
            ("bank_lines.jsonl", ("timestamp",)),
            ("journal_entries.jsonl", ("timestamp",)),
        ):
            p = pub / fname
            rows = _read_jsonl(p)
            for r in rows:
                for tf in ts_fields:
                    if isinstance(r.get(tf), str):
                        r[tf] = _to_utc_equivalent_ts(r[tf])
                if fname == "payments.jsonl":
                    for al in r.get("allocations") or ():
                        if isinstance(al.get("allocation_timestamp"), str):
                            al["allocation_timestamp"] = _to_utc_equivalent_ts(al["allocation_timestamp"])
            _write_jsonl(p, rows)
        return {}

    if transform_id == "M-05":  # json_key_order
        for p in sorted(pub.iterdir()):
            if p.suffix == ".json":
                obj = _reverse_dict_keys(json.loads(p.read_text(encoding="utf-8")))
                p.write_text(json.dumps(obj, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")
            elif p.suffix == ".jsonl":
                rows = [_reverse_dict_keys(r) for r in _read_jsonl(p)]
                lines = [json.dumps(r, sort_keys=False, ensure_ascii=False) for r in rows]
                p.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        return {}

    if transform_id == "M-06":  # equivalent_description
        invs = _read_jsonl(pub / "invoices.jsonl")
        for idx, inv in enumerate(invs):
            for it in inv.get("line_items") or ():
                it["description"] = f"Баламалы сипаттама / Эквивалентное описание #{idx + 1} (ҚҚС-сыз)"
        _write_jsonl(pub / "invoices.jsonl", invs)

        jes = _read_jsonl(pub / "journal_entries.jsonl")
        for idx, je in enumerate(jes):
            je["description"] = f"Бухгалтерлік жазба сипаттамасы #{idx + 1}"
        _write_jsonl(pub / "journal_entries.jsonl", jes)

        bls = _read_jsonl(pub / "bank_lines.jsonl")
        for idx, bl in enumerate(bls):
            bl["reference_text"] = f"Төлем мақсаты баламалы мәтін #{idx + 1}"
        _write_jsonl(pub / "bank_lines.jsonl", bls)
        return {}

    if transform_id == "M-07":  # jsonl_serialization_variants
        for p in sorted(pub.iterdir()):
            if p.suffix == ".json":
                obj = json.loads(p.read_text(encoding="utf-8"))
                p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n\n", encoding="utf-8")
            elif p.suffix == ".jsonl":
                rows = _read_jsonl(p)
                _write_jsonl(p, rows, pretty_ws=True)
        return {}

    raise ValueError(f"unsupported transform_id: {transform_id!r}")


def _canonical_verifier_signature(ep_dir: Path, inv_map: dict[str, str]) -> list[tuple[Any, ...]]:
    disc = discover(ep_dir / "public")
    sigs: list[tuple[Any, ...]] = []
    for f in disc.report.findings:
        aff = tuple(sorted(inv_map.get(a, a) for a in f.affected_ids))
        evs = tuple(
            sorted(tuple(sorted(inv_map.get(e, e) for e in s)) for s in f.evidence_sets)
        )
        sigs.append((f.type, aff, f.currency, f.claimed_amount_minor, evs))
    sigs.sort()
    return sigs


def _eval_budget_aware_reward(ep_dir: Path) -> Fraction:
    env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL"))
    obs = env.reset(ep_dir / "public", cursor_seed=555)
    seq = 0

    def _step(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal seq
        seq += 1
        return env.step(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": f"m-{seq}",
                "action": {"tool": tool, "args": args},
            }
        )

    run_baseline_policy("budget_aware", obs, _step, seed=2025)
    findings = [Finding.from_dict(f) for f in (env.submitted_findings or [])]
    truth_raw = json.loads((ep_dir / "sealed" / "truth.json").read_text(encoding="utf-8"))
    truths = [TruthFinding.from_dict(t) for t in truth_raw]
    return compute_reward(findings, truths, env.steps_used).reward


def run_metamorphic_suite(*, output_path: Path | str | None = None) -> dict[str, Any]:
    out_file = Path(output_path) if output_path else DEFAULT_REPORT_PATH
    transforms = (
        ("M-01", "row_permutation"),
        ("M-02", "id_bijection"),
        ("M-03", "entity_renaming"),
        ("M-04", "timezone_instant_representation"),
        ("M-05", "json_key_order"),
        ("M-06", "equivalent_description"),
        ("M-07", "jsonl_serialization_variants"),
    )

    results: list[dict[str, Any]] = []
    all_passed = True

    with tempfile.TemporaryDirectory(prefix="tl_metamorphic_m01_m07_") as td:
        root = Path(td)
        # Build representative clean + multi-anomaly episodes in non-UTC timezone (Asia/Almaty)
        scenarios = (
            ("ep_meta_clean", ()),
            ("ep_meta_dup_fx", ("DUPLICATE_PAYMENT", "FX_RATE_MISMATCH")),
            ("ep_meta_part_cut", ("PARTIAL_PAYMENT_ALLOCATION", "PERIOD_CUTOFF")),
        )
        base_dirs: list[Path] = []
        for idx, (ep_id, anoms) in enumerate(scenarios):
            spec = CleanTwinSpec(
                episode_id=ep_id,
                master_seed=2025,
                episode_index=80 + idx,
                timezone="Asia/Almaty",
                distractor_classes=("D-DUP-01", "D-FX-01", "D-CUT-01"),
                enable_text_layer=True,
                language_profile="en",
            )
            gen = build_episode(EpisodeRecipe(twin_spec=spec, anomalies=anoms), root / "base")
            base_dirs.append(gen.episode_dir)

        for tid, tname in transforms:
            t_pass = True
            checked_pairs = 0
            pair_details: list[dict[str, Any]] = []
            for base_ep in base_dirs:
                dst_ep = root / tid / base_ep.name
                inv_map = _apply_transform(tid, base_ep, dst_ep)

                sig_orig = _canonical_verifier_signature(base_ep, {})
                sig_trans = _canonical_verifier_signature(dst_ep, inv_map)
                ver_eq = sig_orig == sig_trans

                rew_orig = _eval_budget_aware_reward(base_ep)
                rew_trans = _eval_budget_aware_reward(dst_ep)
                rew_eq = rew_orig == rew_trans

                ok = ver_eq and rew_eq
                t_pass = t_pass and ok
                checked_pairs += 1
                pair_details.append(
                    {
                        "episode_id": base_ep.name,
                        "verifier_equivariant": ver_eq,
                        "reward_invariant": rew_eq,
                        "base_reward": render_decimal(rew_orig),
                        "transformed_reward": render_decimal(rew_trans),
                    }
                )
            all_passed = all_passed and t_pass
            results.append(
                {
                    "transform_id": tid,
                    "name": tname,
                    "status": "PASS" if t_pass else "FAIL",
                    "pairs_checked": checked_pairs,
                    "details": pair_details,
                }
            )

    cfg_meta = {"transforms": [t[0] for t in transforms], "scenarios": [s[0] for s in scenarios]}
    report = {
        "schema_version": "1.0.0",
        "report_type": "metamorphic_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(cfg_meta),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 metamorphic/suite.py",
        "status": "PASS" if all_passed else "FAIL",
        "summary": {
            "transforms_total": len(results),
            "transforms_passed": sum(1 for r in results if r["status"] == "PASS"),
            "total_episode_pairs_verified": sum(int(r["pairs_checked"]) for r in results),
        },
        "transforms": results,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(canonical_json(report) + "\n", encoding="utf-8")
    return report


def main() -> int:
    rep = run_metamorphic_suite()
    s = rep["summary"]
    print(
        f"[{rep['status']}] metamorphic suite: {s['transforms_passed']}/{s['transforms_total']} "
        f"transforms passed ({s['total_episode_pairs_verified']} pairs) -> {DEFAULT_REPORT_PATH}"
    )
    return 0 if rep["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
