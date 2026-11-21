"""Post-termination isolated scorer subprocess entrypoint (Phase 9, Task 9.3).

Invoked as a separate OS process AFTER ``env`` and ``policy`` processes have
terminated and closed (REQ-ARC-005, REQ-SEAL-003):

  python3 -m scoring.scorer_cli score \\
      --episode-dir <episode_dir> \\
      --submission <submission.json> \\
      --trajectory <trajectory.json> \\
      --policy-id <policy_identifier> \\
      --output-receipt <receipt.json> \\
      --output-score <score_report.json>

  python3 -m scoring.scorer_cli seal-batch \\
      --receipts <r1.json> <r2.json> ... \\
      --output-summary <merkle_batch.json>

Imports ONLY ``contracts/``, ``seal/``, ``scoring/``, ``nlp.hierarchy``
(the strict TZ §17.3 evidence-hierarchy rule module — never the optional fuzzy
helpers ``nlp.matching`` / ``nlp.normalize``), and Python 3.11 stdlib
(obeys ``scoring/`` import boundaries).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from contracts.canonical import canonical_bytes, canonical_json, sha256_hex
from contracts.loader import validate_instance
from contracts.models import Finding, TruthFinding
from nlp.hierarchy import build_evidence_hierarchy_report
from scoring.crosscheck import CrosscheckError, crosscheck
from scoring.diagnostics import build_diagnostics
from scoring.explanation_linter import lint_findings_explanations
from scoring.matcher import optimal_matching
from scoring.official_scorer import (
    collect_accessible_ids_from_episode_dir,
    load_truths_from_episode_dir,
    score_official_findings,
)
from scoring.reward import compute_reward, load_scoring_config
from seal.commitment import verify_reveal
from seal.hashchain import verify_hash_chain
from seal.receipt import (
    build_lineage_digests,
    build_receipt,
    compute_code_version_hash,
    compute_manifest_hash,
    seal_receipt_batch,
)


def _verify_public_manifest_files(episode_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Verify ``manifest.json`` schema and every listed public file's SHA-256."""
    errors = validate_instance("episode_manifest", manifest)
    if errors:
        return errors
    for item in manifest.get("public_files", []):
        rel = item["path"]
        target = episode_dir / rel
        if not target.is_file():
            errors.append(f"missing public file {rel}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != item["sha256"]:
            errors.append(f"public file sha256 mismatch for {rel}")
    return errors


def _load_trajectory_bundle(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Load ``trajectory_event`` list and optional ``trajectory_head`` from JSON or JSONL."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        events: list[dict[str, Any]] = []
        head: str | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict) and "trajectory_event" in obj:
                events.append(obj["trajectory_event"])
                if isinstance(obj.get("chain_head_after"), str):
                    head = obj["chain_head_after"]
            elif isinstance(obj, dict) and "event_index" in obj:
                events.append(obj)
        return events, head

    data = json.loads(text)
    if isinstance(data, dict):
        return list(data.get("events", [])), data.get("trajectory_head")
    if isinstance(data, list):
        return list(data), None
    raise ValueError(f"unsupported trajectory format in {path}")


def _extract_raw_findings_list(findings_payload: Any) -> list[dict[str, Any]] | None:
    if findings_payload is None:
        return []
    if isinstance(findings_payload, dict) and isinstance(findings_payload.get("findings"), list):
        return list(findings_payload["findings"])
    if isinstance(findings_payload, list):
        return list(findings_payload)
    return None


def _coerce_contract_findings(raw_findings: list[dict[str, Any]] | None) -> list[Finding] | None:
    """Parse findings into frozen ``contracts/finding.schema.json`` models when compatible."""
    if raw_findings is None:
        return None
    out: list[Finding] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            return None
        candidate = dict(item)
        candidate.setdefault("schema_version", "1.0.0")
        if "claimed_amount" not in candidate and "claimed_amount_minor" in candidate:
            candidate["claimed_amount"] = candidate.pop("claimed_amount_minor")
        try:
            out.append(Finding.from_dict(candidate))
        except ValueError:
            return None
    return out


def execute_score_episode(
    *,
    episode_dir: Path,
    submission_path: Path,
    trajectory_path: Path,
    policy_id: str,
    output_receipt_path: Path,
    output_score_path: Path,
    merkle_leaf_index: int = 0,
    salt_mode: str = "TEST_FIXTURE",
    reveal_salt_in_receipt: bool = False,
) -> tuple[int, dict[str, Any]]:
    """Run commit-reveal, hash-chain verification, deterministic scoring, and receipt sealing."""
    manifest_path = episode_dir / "manifest.json"
    truth_path = episode_dir / "sealed" / "truth.json"
    prov_path = episode_dir / "sealed" / "provenance.json"

    if not manifest_path.is_file() or not truth_path.is_file() or not prov_path.is_file():
        return 2, {"ok": False, "error": "missing manifest.json or sealed truth/provenance"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_errs = _verify_public_manifest_files(episode_dir, manifest)
    if manifest_errs:
        return 4, {"ok": False, "error": f"manifest integrity failed: {manifest_errs[0]}"}

    truths_raw = json.loads(truth_path.read_text(encoding="utf-8"))
    provenance = json.loads(prov_path.read_text(encoding="utf-8"))
    salt_hex = str(provenance.get("commitment_salt_hex", ""))
    effective_salt_mode = str(provenance.get("salt_mode") or salt_mode)
    if effective_salt_mode not in ("PRODUCTION_SECRET", "TEST_FIXTURE"):
        effective_salt_mode = salt_mode

    # 1. Commit-reveal check (REQ-SEAL-010..013)
    reveal_res = verify_reveal(
        manifest["truth_commitment"],
        truths_raw,
        salt_hex,
        salt_mode=effective_salt_mode,
    )

    # 2. Trajectory hash-chain check (REQ-SEAL-021)
    events, expected_head = _load_trajectory_bundle(trajectory_path)
    chain_res = verify_hash_chain(
        manifest["truth_commitment"],
        manifest["episode_id"],
        events,
        expected_head=expected_head,
    )

    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    steps_used = int(submission.get("steps_used", 0))
    findings_payload = submission.get("findings", [])
    terminated = bool(submission.get("terminated", False))
    truncated = bool(submission.get("truncated", False))
    no_submit = bool(submission.get("no_submit", not terminated))
    timed_out = bool(submission.get("timed_out", False))
    isolation_profile = submission.get("isolation_profile")

    # 3. Official 2026-11-20 scoring
    official_truths = load_truths_from_episode_dir(episode_dir)
    accessible_ids = collect_accessible_ids_from_episode_dir(episode_dir)
    official_res = score_official_findings(
        findings_payload,
        official_truths,
        steps_used,
        accessible_ids=accessible_ids,
    )

    # 4. Stage-2 semantic truth crosscheck against independent verifier_report.json (L4 fix)
    truth_models = [TruthFinding.from_dict(t) for t in truths_raw]
    verifier_report_path = episode_dir / "verifier_report.json"
    semantic_truth_ok = True
    verifier_quality_block: dict[str, Any] | None = None
    semantic_truth_block: dict[str, Any]
    if verifier_report_path.is_file():
        try:
            v_rep = json.loads(verifier_report_path.read_text(encoding="utf-8"))
            cc_res = crosscheck(v_rep, truth_models)
            verifier_quality_block = cc_res.to_dict()
            semantic_truth_ok = not cc_res.release_blocked
            semantic_truth_block = {
                "status": "VERIFIED" if semantic_truth_ok else "REJECTED",
                "release_blocked": cc_res.release_blocked,
                "blocking_reasons": list(cc_res.blocking_reasons),
                "verifier_report_hash": cc_res.verifier_report_hash,
                "crosscheck_hash": cc_res.crosscheck_hash,
            }
        except (CrosscheckError, ValueError) as exc:
            semantic_truth_ok = False
            semantic_truth_block = {
                "status": "REJECTED",
                "release_blocked": True,
                "blocking_reasons": [str(exc)],
            }
    else:
        semantic_truth_block = {
            "status": "SKIPPED_NO_VERIFIER_REPORT",
            "release_blocked": False,
            "blocking_reasons": [],
        }

    # 5. Frozen v1.0.0 contract scoring + explanation linter + verifier quality diagnostics
    raw_list = _extract_raw_findings_list(findings_payload)
    contract_findings = _coerce_contract_findings(raw_list)
    scoring_cfg = load_scoring_config()
    contract_score_block: dict[str, Any]
    if contract_findings is not None and 0 <= steps_used <= scoring_cfg.max_steps:
        match_res = optimal_matching(contract_findings, truth_models)
        reward_bd = compute_reward(
            contract_findings,
            truth_models,
            steps_used=steps_used,
            config=scoring_cfg,
            match_result=match_res,
        )
        expl_lint = lint_findings_explanations(
            contract_findings,
            accessible_public_ids=accessible_ids,
        )
        # Phase 10, Task 10.5 enforcement: TZ §17.3 evidence hierarchy verdict per
        # finding (structural reachability only — no fuzzy matching). Diagnostic
        # only: it never alters matching, F1, or the official reward.
        evidence_hierarchy = build_evidence_hierarchy_report(
            contract_findings,
            accessible_public_ids=accessible_ids,
        )
        run_info: dict[str, Any] = {
            "steps_used": steps_used,
            "truncated": truncated,
            "no_submit": no_submit,
            "timeout": timed_out,
            "policy_identifier": policy_id,
            "requested_evidence_ids": submission.get("requested_evidence_ids"),
            "explanation_consistency": expl_lint,
            "evidence_hierarchy": evidence_hierarchy,
        }
        if verifier_quality_block is not None:
            run_info["verifier_quality"] = verifier_quality_block
        diag = build_diagnostics(
            contract_findings,
            truth_models,
            match_res,
            reward_bd,
            run_info=run_info,
        )
        contract_score_block = {
            "available": True,
            "reward_breakdown": reward_bd.to_dict(),
            "diagnostics": diag,
        }
    else:
        contract_score_block = {
            "available": False,
            "reason": "submission used non-typed or structurally invalid findings outside v1.0.0 contract",
        }

    integrity_ok = reveal_res.verified and chain_res.valid and semantic_truth_ok
    verification_status = "VERIFIED" if integrity_ok else "REJECTED"

    score_report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "episode_id": manifest["episode_id"],
        "policy_identifier": policy_id,
        "verification_status": verification_status,
        "steps_used": steps_used,
        "terminated": terminated,
        "truncated": truncated,
        "no_submit": no_submit,
        "timed_out": timed_out,
        "commit_reveal": reveal_res.to_dict(),
        "semantic_truth_verification": semantic_truth_block,
        "trajectory_verification": chain_res.to_dict(),
        "official_score": official_res.to_score_dict(),
        "official_valid": official_res.valid,
        "official_error": official_res.error,
        "contract_v1_score": contract_score_block,
        "salt_reveal": {
            "mode": effective_salt_mode,
            "salt_hex": salt_hex,
        },
    }
    scorer_report_hash = sha256_hex(score_report)

    verifier_report_hash = (
        sha256_hex(json.loads(verifier_report_path.read_text(encoding="utf-8")))
        if verifier_report_path.is_file()
        else None
    )
    diff_hash = (
        sha256_hex(provenance["structural_diff"])
        if "structural_diff" in provenance
        else None
    )
    public_manifest_hash = compute_manifest_hash(manifest)
    code_hash = compute_code_version_hash()

    lineage = build_lineage_digests(
        generator_version=manifest["generator_version"],
        config_hash=manifest["config_hash"],
        public_manifest_hash=public_manifest_hash,
        truth_commitment=manifest["truth_commitment"],
        trajectory_head=chain_res.computed_head,
        verifier_report_hash=verifier_report_hash,
        scorer_report_hash=scorer_report_hash,
        mutation_diff_hash=diff_hash,
    )

    salt_ref: str | dict[str, Any] = (
        {"mode": salt_mode, "salt_hex": salt_hex}
        if reveal_salt_in_receipt
        else "SEALED"
    )
    receipt = build_receipt(
        episode_id=manifest["episode_id"],
        code_version_hash=code_hash,
        config_hash=manifest["config_hash"],
        public_manifest_hash=public_manifest_hash,
        truth_commitment=manifest["truth_commitment"],
        trajectory_head=chain_res.computed_head,
        policy_identifier=policy_id,
        merkle_leaf_index=merkle_leaf_index,
        verification_status=verification_status,
        salt_reveal_ref=salt_ref,
        reward_breakdown_ref=scorer_report_hash,
        isolation_profile=isolation_profile if isinstance(isolation_profile, dict) else None,
        lineage=lineage,
    )

    output_score_path.parent.mkdir(parents=True, exist_ok=True)
    output_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output_score_path.write_bytes(canonical_bytes(score_report))
    output_receipt_path.write_bytes(canonical_bytes(receipt))

    exit_code = 0 if integrity_ok else 4
    summary = {
        "ok": integrity_ok,
        "episode_id": manifest["episode_id"],
        "verification_status": verification_status,
        "trajectory_head": chain_res.computed_head,
        "merkle_root": receipt["x_twinledger_merkle_root"],
        "scorer_report_hash": scorer_report_hash,
        "official_score": official_res.to_score_dict(),
        "contract_reward_exact": (
            contract_score_block["reward_breakdown"]["reward_exact"]
            if contract_score_block["available"]
            else None
        ),
    }
    return exit_code, summary


def _cmd_seal_batch(receipt_paths: list[Path], output_summary: Path | None) -> int:
    loaded = [json.loads(p.read_text(encoding="utf-8")) for p in receipt_paths]
    root, updated = seal_receipt_batch(loaded)
    for p, rec in zip(receipt_paths, updated):
        p.write_bytes(canonical_bytes(rec))
    batch_summary = {
        "schema_version": "1.0.0",
        "merkle_root": root,
        "leaf_count": len(updated),
        "leaves": [
            {
                "merkle_leaf_index": rec["merkle_leaf_index"],
                "episode_id": rec["episode_id"],
                "policy_identifier": rec["policy_identifier"],
                "trajectory_head": rec["trajectory_head"],
            }
            for rec in updated
        ],
    }
    if output_summary is not None:
        output_summary.parent.mkdir(parents=True, exist_ok=True)
        output_summary.write_bytes(canonical_bytes(batch_summary))
    sys.stdout.write(canonical_json(batch_summary) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger isolated post-episode scorer CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("score", help="Score a completed episode and emit receipt + score report")
    sc.add_argument("--episode-dir", required=True)
    sc.add_argument("--submission", required=True)
    sc.add_argument("--trajectory", required=True)
    sc.add_argument("--policy-id", required=True)
    sc.add_argument("--output-receipt", required=True)
    sc.add_argument("--output-score", required=True)
    sc.add_argument("--merkle-leaf-index", type=int, default=0)
    sc.add_argument("--salt-mode", default="TEST_FIXTURE", choices=["PRODUCTION_SECRET", "TEST_FIXTURE"])
    sc.add_argument("--reveal-salt", action="store_true")

    sb = sub.add_parser("seal-batch", help="Build batch Merkle tree over receipts and embed proofs")
    sb.add_argument("--receipts", nargs="+", required=True)
    sb.add_argument("--output-summary", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "seal-batch":
        return _cmd_seal_batch(
            [Path(p) for p in args.receipts],
            Path(args.output_summary) if args.output_summary else None,
        )

    code, summary = execute_score_episode(
        episode_dir=Path(args.episode_dir),
        submission_path=Path(args.submission),
        trajectory_path=Path(args.trajectory),
        policy_id=args.policy_id,
        output_receipt_path=Path(args.output_receipt),
        output_score_path=Path(args.output_score),
        merkle_leaf_index=args.merkle_leaf_index,
        salt_mode=args.salt_mode,
        reveal_salt_in_receipt=bool(args.reveal_salt),
    )
    sys.stdout.write(canonical_json(summary) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
