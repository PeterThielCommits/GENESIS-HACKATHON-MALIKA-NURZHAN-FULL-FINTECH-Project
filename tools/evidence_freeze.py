#!/usr/bin/env python3
"""Post-release evidence freeze (Phase 17, Master TZ section 24, tasks 17.1-17.3).

The *contract* freeze (``tools/freeze_release.py``) pins the 30 frozen
contract surfaces. This tool pins the **whole release surface**, so that the
release can be reconstructed and verified from the repository alone
(EXIT GATE 17: "the release can be restored and checked without oral
explanations from the team").

What is archived (Master TZ section 24):

  17.1  final code version + config hashes - every tracked file (runtime
        code, configs, contracts, rubric map, Dockerfile, Makefile,
        entrypoint, episodes, docs) hashed with SHA-256.
  17.2  verify + replay reports - the Judge Kit verdicts (verify_summary,
        replay_report, report_index, release_audit, doc_claims,
        trajectory_replay) are archived as *verdicts* (status + counts).
        Report bytes carry timestamps/run-ids and are regenerable, so
        byte-identity is **not** required on re-run; the verdict is the
        archived fact.
  17.3  final rubric map + decisions - both are tracked files and therefore
        hashed by 17.1 (``judge/rubric_map.json``, ``docs/DECISIONS.md``).

The manifest (``docs/EVIDENCE/evidence_freeze.json``) is committed to the
repository. It lives **outside** ``configs/`` on purpose: any new file under
``configs/`` would itself drift the contract freeze
(``tools/freeze_release.py``), which must stay at 30 files /
``0747baf0...``.

Design rules (learned in Phases 15-16):
  * Stdlib only, offline, deterministic (sorted paths, canonical JSON).
  * Console output is ASCII-safe (the hardened container runs ``LC_ALL=C``).
  * The manifest excludes itself from its own hash list.
  * ``git_commit`` / ``generated_at_utc`` are informational anchors; they are
    never compared on verify, because a later commit with an identical tree
    must still verify.
  * Report **bytes** are informational; report **verdicts** are enforced.
  * Verdict extraction keeps only stable, status-level facts. A detail string
    such as "540 text files scanned" would drift the moment the tree grows,
    so counts that depend on the tree are deliberately excluded.

Modes:
  python3 tools/evidence_freeze.py --write     write docs/EVIDENCE/evidence_freeze.json
  python3 tools/evidence_freeze.py --verify    verify zero drift (exit 0/4/2)
  python3 tools/evidence_freeze.py --json      machine-readable summary

Exit codes (TZ 23.3 style):
  0  PASS (verify) / written (write)
  2  configuration error (manifest missing/unreadable, required report missing)
  4  drift detected (tracked file changed/added/removed, or verdict mismatch)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import canonical_json

DEFAULT_MANIFEST = REPO_ROOT / "docs" / "EVIDENCE" / "evidence_freeze.json"

#: Reports produced by ``make verify`` / ``make report`` (the Judge Kit
#: evidence set, TZ 23.5). They are REQUIRED: a verification that cannot
#: read them is not a verification.
REQUIRED_REPORTS: dict[str, str] = {
    "verify_summary": "artifacts/reports/latest/verify_summary.json",
    "replay_report": "artifacts/reports/latest/replay_report.json",
    "report_index": "artifacts/reports/latest/report_index.json",
}

#: Reports produced by other release targets. Archived when present; compared
#: when present at verify time; a missing optional report is not an error
#: (the target that produces it was simply not run).
OPTIONAL_REPORTS: dict[str, str] = {
    "release_audit": "artifacts/reports/release/release_audit.json",
    "doc_claims": "artifacts/reports/doc_claims/doc_claims_report.json",
    "trajectory_replay": "artifacts/reports/release/trajectory_replay.json",
}

REPORT_FILES: dict[str, str] = {**REQUIRED_REPORTS, **OPTIONAL_REPORTS}

#: Directories that are never part of the tracked release surface.
_EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def _say(message: str) -> None:
    """ASCII-safe console write (the hardened container runs ``LC_ALL=C``)."""
    transliterated = (
        message.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2192", "->")
        .replace("\u00a7", "S")
        .replace("\u2264", "<=")
        .replace("\u2265", ">=")
    )
    try:
        print(transliterated)
    except UnicodeEncodeError:  # pragma: no cover - last-resort guard
        print(transliterated.encode("ascii", "replace").decode("ascii"))


# --------------------------------------------------------------------------- #
# verdict extraction - stable, status-level facts only
# --------------------------------------------------------------------------- #
def _check_statuses(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """``[{"id": ..., "status": ...}]`` for any report with a check list."""
    out: list[dict[str, Any]] = []
    for entry in doc.get("checks") or []:
        if isinstance(entry, dict):
            out.append(
                {
                    "id": entry.get("id") or entry.get("check_id") or entry.get("rubric_item"),
                    "status": entry.get("status"),
                }
            )
    return out


def _extract_verdict(name: str, doc: Any) -> dict[str, Any]:
    """Reduce a report to the facts that must not change on a re-run."""
    if not isinstance(doc, dict):
        return {"readable": False}
    if name == "verify_summary":
        checks = doc.get("checks") or []
        return {
            "status": doc.get("status"),
            "official_score_claimed": doc.get("official_score_claimed"),
            "internal_pass_rate_pct": doc.get("internal_pass_rate_pct"),
            "required_checks": doc.get("required_checks"),
            "optional_checks": doc.get("optional_checks"),
            "missing_artifacts": list(doc.get("missing_artifacts") or []),
            "gates": [
                {
                    "check_id": c.get("check_id"),
                    "status": c.get("status"),
                    "required": c.get("required"),
                    "release_blocker": c.get("release_blocker"),
                }
                for c in checks
                if isinstance(c, dict)
            ],
        }
    if name == "replay_report":
        return {
            "status": doc.get("status"),
            "episodes_replayed": doc.get("episodes_replayed"),
            "episodes_tested": doc.get("episodes_tested"),
            "episodes_matched": doc.get("episodes_matched"),
            "all_byte_identical": doc.get("all_byte_identical"),
            "all_hashes_identical": doc.get("all_hashes_identical"),
            "all_rewards_identical": doc.get("all_rewards_identical"),
            "all_receipts_verified_offline": doc.get("all_receipts_verified_offline"),
            "batch_merkle_root": doc.get("batch_merkle_root"),
        }
    if name == "report_index":
        return {
            "verify_status": doc.get("verify_status"),
            "offline_self_contained_html": doc.get("offline_self_contained_html"),
            "missing_optional_or_full_mode_artifacts": list(
                doc.get("missing_optional_or_full_mode_artifacts") or []
            ),
            "artifact_count": len(doc.get("artifacts") or []),
        }
    if name == "release_audit":
        return {
            "status": doc.get("status"),
            "exit_code": doc.get("exit_code"),
            "failed_count": len(doc.get("failed") or []),
            "checks": _check_statuses(doc),
        }
    if name == "doc_claims":
        return {
            "status": doc.get("status"),
            "checks_passed": doc.get("checks_passed"),
            "checks_total": doc.get("checks_total"),
            "facts_total": doc.get("facts_total"),
            "failure_count": len(doc.get("failures") or []),
            "checks": _check_statuses(doc),
        }
    if name == "trajectory_replay":
        return {
            "status": doc.get("status"),
            "runs_replayed": doc.get("runs_replayed"),
            "runs_matched": doc.get("runs_matched"),
            "steps_replayed": doc.get("steps_replayed"),
            "failure_count": len(doc.get("failures") or []),
        }
    return {"readable": False}


# --------------------------------------------------------------------------- #
# file hashing
# --------------------------------------------------------------------------- #
def _git_commit(repo_root: Path) -> str:
    """HEAD commit, or a stable marker when ``.git`` is absent (tarball case)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
            return sha
    except Exception:
        pass
    return "unknown (no .git)"


def _tracked_paths(repo_root: Path) -> list[Path]:
    """Tracked release-surface files (``git ls-files``, with a walk fallback)."""
    manifest = (repo_root / "docs" / "EVIDENCE" / "evidence_freeze.json").resolve()
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            paths: list[Path] = []
            for line in out.stdout.splitlines():
                candidate = (repo_root / line.strip()).resolve()
                if candidate.is_file() and candidate != manifest:
                    paths.append(candidate)
            return sorted(paths, key=lambda p: p.relative_to(repo_root).as_posix())
    except Exception:
        pass
    # Fallback (git archive / tarball): walk the tree, skipping generated output.
    paths = []
    for candidate in sorted(repo_root.rglob("*")):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(repo_root)
        if any(part in _EXCLUDED_DIRS for part in rel.parts):
            continue
        rel_posix = rel.as_posix()
        if rel_posix.startswith(("artifacts/reports/latest/", "artifacts/reports/doc_claims/",
                                  "artifacts/reports/release/", "artifacts/reports/evaluation/")):
            continue
        if candidate.resolve() == manifest:
            continue
        paths.append(candidate)
    return sorted(paths, key=lambda p: p.relative_to(repo_root).as_posix())


def _file_entry(repo_root: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _report_entry(name: str, rel: str, repo_root: Path) -> dict[str, Any]:
    """Archived verdict for one generated report (raw bytes informational)."""
    path = repo_root / rel
    entry: dict[str, Any] = {
        "path": rel,
        "required": name in REQUIRED_REPORTS,
        "present": path.is_file(),
        "sha256": None,
        "verdict": None,
    }
    if not path.is_file():
        return entry
    raw = path.read_bytes()
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except Exception:
        doc = None
    entry["verdict"] = _extract_verdict(name, doc)
    return entry


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def compute_manifest(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build the evidence-freeze manifest for the current tree."""
    entries = [_file_entry(repo_root, p) for p in _tracked_paths(repo_root)]
    reports = {name: _report_entry(name, rel, repo_root) for name, rel in REPORT_FILES.items()}
    verdict_view = {
        name: (rep["verdict"] if rep["present"] else None) for name, rep in reports.items()
    }
    aggregate = hashlib.sha256(
        canonical_json({"files": entries, "reports": verdict_view}).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.0.0",
        "phase": 17,
        "code_version": "twinledger@1.0.0",
        "official_score_claimed": False,
        "source_commit": _git_commit(repo_root),
        "anchor_note": (
            "aggregate_sha256 identifies the archived tree and is "
            "commit-independent; source_commit is the HEAD the working tree "
            "was based on when the archive was generated (the archive is "
            "written before the commit that carries it)."
        ),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "frozen_file_count": len(entries),
        "aggregate_sha256": aggregate,
        "files": entries,
        "reports": reports,
    }


def verify_manifest(
    manifest_path: Path = DEFAULT_MANIFEST, repo_root: Path = REPO_ROOT
) -> tuple[bool, list[str]]:
    """Verify zero drift against the committed manifest.

    Tracked-file hashes are strict. Required reports must be present with the
    archived verdict; optional reports are compared when present and skipped
    when the producing target was not run.
    """
    if not manifest_path.is_file():
        return False, [f"missing evidence manifest: {manifest_path}"]
    try:
        expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"unreadable evidence manifest: {exc}"]

    current = compute_manifest(repo_root)
    errors: list[str] = []

    exp_map = {e["path"]: e["sha256"] for e in expected.get("files", [])}
    cur_map = {e["path"]: e["sha256"] for e in current.get("files", [])}
    for path_key in sorted(set(exp_map) | set(cur_map)):
        if path_key not in exp_map:
            errors.append(f"untracked new file in release surface: {path_key}")
        elif path_key not in cur_map:
            errors.append(f"missing release file: {path_key}")
        elif exp_map[path_key] != cur_map[path_key]:
            errors.append(
                f"SHA-256 drift in release file {path_key}: "
                f"expected {exp_map[path_key]}, got {cur_map[path_key]}"
            )

    exp_reports = expected.get("reports", {})
    cur_reports = current.get("reports", {})
    for name in sorted(set(exp_reports) | set(cur_reports)):
        exp = exp_reports.get(name) or {}
        cur = cur_reports.get(name) or {}
        required = bool(exp.get("required") or cur.get("required"))
        if exp.get("present") and not cur.get("present"):
            if required:
                errors.append(
                    f"report missing (run `make verify` first): {name} ({cur.get('path')})"
                )
            continue
        if exp.get("present") and cur.get("present"):
            if exp.get("verdict") != cur.get("verdict"):
                errors.append(f"report verdict drift: {name}")

    if expected.get("aggregate_sha256") != current.get("aggregate_sha256"):
        errors.append("aggregate_sha256 mismatch")
    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger Phase 17 evidence freeze")
    parser.add_argument("--write", action="store_true", help="Write/update docs/EVIDENCE/evidence_freeze.json")
    parser.add_argument("--verify", action="store_true", help="Verify zero drift against the manifest")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable summary")
    args = parser.parse_args(argv)

    if args.write:
        doc = compute_manifest()
        DEFAULT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_MANIFEST.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _say(
            f"[PASS] evidence_freeze --write: {doc['frozen_file_count']} files frozen "
            f"(aggregate_sha256={doc['aggregate_sha256'][:16]}...) -> {DEFAULT_MANIFEST}"
        )
        return 0

    ok, errs = verify_manifest()
    if args.json:
        summary = {
            "status": "PASS" if ok else "FAIL",
            "manifest": str(DEFAULT_MANIFEST.relative_to(REPO_ROOT)),
            "errors": errs,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if ok else 4

    if ok:
        doc = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        _say(
            f"[PASS] evidence_freeze --verify: {doc['frozen_file_count']} release files intact "
            f"(aggregate_sha256={doc['aggregate_sha256'][:16]}...)"
        )
        return 0
    _say(f"[FAIL] evidence_freeze --verify ({len(errs)} errors):")
    for err in errs:
        _say(f"  - {err}")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
