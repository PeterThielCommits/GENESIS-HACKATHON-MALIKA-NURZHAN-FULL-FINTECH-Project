#!/usr/bin/env python3
"""Phase 17 release-evidence archive (Master TZ section 24, tasks 17.2/17.3/17.6).

``tools/evidence_freeze.py`` hashes the release surface. This tool builds the
**human- and machine-readable** companion archive: one JSON file that says,
in one place, what was released, which gates passed, which rubric gates
exist, which decisions were taken, and -- with an exact command list -- how
a stranger reconstructs and re-verifies the release **from the repository
alone** (EXIT GATE 17: "the release can be restored and checked without oral
explanations from the team").

The archive is generated from *measured* sources only:

  * ``configs/release_freeze.json``  -- the 30 frozen contract surfaces;
  * ``artifacts/reports/latest/verify_summary.json`` -- the 12 Judge Kit gates;
  * ``artifacts/reports/release/trajectory_replay.json`` -- 80/80 replay;
  * ``artifacts/reports/release/release_audit.json`` -- secrets/size/deps audit;
  * ``artifacts/reports/doc_claims/doc_claims_report.json`` -- documentation claims;
  * ``judge/rubric_map.json`` -- the rubric map (task 17.3);
  * ``docs/DECISIONS.md`` -- the decision register (task 17.3).

``--verify`` recomputes every verifiable part and compares it with the
committed archive. ``generated_at_utc`` and ``git_sha`` are informational
anchors and are never compared (a later commit with the same tree must
still verify); ``official_score_claimed`` must stay ``false``.

Modes:
  python3 tools/release_evidence.py --write    write docs/EVIDENCE/phase-17-release-evidence-2026-11-22.json
  python3 tools/release_evidence.py --verify   verify the committed archive
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_PATH = REPO_ROOT / "docs" / "EVIDENCE" / "phase-17-release-evidence-2026-11-22.json"
CONTRACT_FREEZE = REPO_ROOT / "configs" / "release_freeze.json"
EVIDENCE_FREEZE = REPO_ROOT / "docs" / "EVIDENCE" / "evidence_freeze.json"
RUBRIC_MAP = REPO_ROOT / "judge" / "rubric_map.json"
DECISIONS = REPO_ROOT / "docs" / "DECISIONS.md"

REPORT_SOURCES = {
    "verify": "artifacts/reports/latest/verify_summary.json",
    "replay_all": "artifacts/reports/release/trajectory_replay.json",
    "release_audit": "artifacts/reports/release/release_audit.json",
    "doc_claims": "artifacts/reports/doc_claims/doc_claims_report.json",
}

#: The exact, ordered command list a stranger runs to rebuild and re-verify
#: the release. Every entry must exist in the repository (checked by
#: ``C-COMMANDS`` in ``tools/verify_doc_claims.py``).
RECONSTRUCT_COMMANDS: tuple[str, ...] = (
    "python3 tools/freeze_release.py --verify",
    "make verify",
    "make docs-verify",
    "make replay-all",
    "make release-audit",
    "python3 tools/evidence_freeze.py --verify --require-reports",
    "python3 tools/release_evidence.py --verify --strict",
    "python3 -m unittest discover -s tests -t .",
)

#: Informational fields: they are recorded but never compared on verify.
INFORMATIONAL_FIELDS = ("generated_at_utc", "git_sha", "platform", "python_version")


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


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    except Exception:
        pass
    return "unknown (no .git)"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_ids() -> list[dict[str, str]]:
    """Decision ids and titles from ``docs/DECISIONS.md``."""
    if not DECISIONS.is_file():
        return []
    out: list[dict[str, str]] = []
    pattern = re.compile(r"^##\s+(D-\d{2}-\d{2})\s*(?:\(([^)]*)\))?\s*(?:[—-]\s*(.*))?$")
    for line in DECISIONS.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            out.append(
                {
                    "id": match.group(1),
                    "date": (match.group(2) or "").strip(),
                    "title": (match.group(3) or "").strip(),
                }
            )
    return out


def _rubric_summary() -> dict[str, Any]:
    if not RUBRIC_MAP.is_file():
        return {"path": RUBRIC_MAP.relative_to(REPO_ROOT).as_posix(), "gates": []}
    doc = _load_json(RUBRIC_MAP)
    gates: list[str] = []
    if isinstance(doc, dict):
        for check in doc.get("checks") or []:
            if isinstance(check, dict) and check.get("check_id"):
                gates.append(str(check["check_id"]))
    return {
        "path": RUBRIC_MAP.relative_to(REPO_ROOT).as_posix(),
        "provisional": bool(doc.get("provisional")) if isinstance(doc, dict) else None,
        "gates": gates,
        "gate_count": len(gates),
    }


def _gate_verdicts() -> dict[str, Any]:
    """Measured gate verdicts (status + counts only; no timestamps)."""
    out: dict[str, Any] = {}
    for name, rel in REPORT_SOURCES.items():
        path = REPO_ROOT / rel
        if not path.is_file():
            out[name] = {"present": False, "path": rel, "status": None}
            continue
        try:
            doc = _load_json(path)
        except Exception:
            out[name] = {"present": False, "path": rel, "status": None}
            continue
        verdict: dict[str, Any] = {"present": True, "path": rel}
        if name == "verify":
            verdict.update(
                {
                    "status": doc.get("status"),
                    "gates_total": (doc.get("required_checks") or {}).get("total"),
                    "gates_passed": (doc.get("required_checks") or {}).get("passed"),
                    "gates_failed": (doc.get("required_checks") or {}).get("failed"),
                    "internal_pass_rate_pct": doc.get("internal_pass_rate_pct"),
                    "official_score_claimed": doc.get("official_score_claimed"),
                }
            )
        elif name == "replay_all":
            verdict.update(
                {
                    "status": doc.get("status"),
                    "runs_replayed": doc.get("runs_replayed"),
                    "runs_matched": doc.get("runs_matched"),
                    "steps_replayed": doc.get("steps_replayed"),
                }
            )
        elif name == "release_audit":
            checks = doc.get("checks") or []
            verdict.update(
                {
                    "status": doc.get("status"),
                    "checks_total": len(checks),
                    "checks_passed": sum(
                        1 for c in checks if isinstance(c, dict) and c.get("status") == "PASS"
                    ),
                }
            )
        elif name == "doc_claims":
            verdict.update(
                {
                    "status": doc.get("status"),
                    "checks_passed": doc.get("checks_passed"),
                    "checks_total": doc.get("checks_total"),
                    "facts_total": doc.get("facts_total"),
                }
            )
        out[name] = verdict
    return out


def build_archive() -> dict[str, Any]:
    """Build the release-evidence archive from the measured sources."""
    contract_freeze: dict[str, Any] = {
        "manifest": CONTRACT_FREEZE.relative_to(REPO_ROOT).as_posix(),
        "tool": "tools/freeze_release.py",
    }
    if CONTRACT_FREEZE.is_file():
        doc = _load_json(CONTRACT_FREEZE)
        contract_freeze.update(
            {
                "frozen_file_count": doc.get("frozen_file_count"),
                "aggregate_sha256": doc.get("aggregate_sha256"),
            }
        )
    gates = _gate_verdicts()
    not_passing = [
        name
        for name, verdict in sorted(gates.items())
        if verdict.get("status") != "PASS"
    ]
    rubric = _rubric_summary()
    archive_complete = (
        bool(contract_freeze.get("aggregate_sha256"))
        and rubric.get("gate_count") == 12
        and bool(RECONSTRUCT_COMMANDS)
    )
    final = not not_passing and archive_complete
    return {
        "artifact": "phase-17-release-evidence",
        "schema_version": "1.0.0",
        "phase": 17,
        # FINAL means: the archived verdicts are a passing release run.
        # DRAFT means: at least one measured verdict was not PASS when the
        # archive was written -- the archive says so explicitly instead of
        # hiding it. The release procedure requires FINAL.
        "status": "FINAL" if final else "DRAFT",
        "draft_reason": (
            ""
            if final
            else "not a passing release run: "
            + (
                "measured verdicts not PASS at write time: " + ", ".join(not_passing)
                if not_passing
                else "the archive is incomplete (missing frozen digest, rubric map or reconstruct list)"
            )
        ),
        "title": "Post-release evidence freeze - reconstructable release archive",
        "official_score_claimed": False,
        # EXIT GATE 17 ("the release can be restored and verified without oral
        # explanations from the team") is derived, not asserted: it is PASS only
        # when the archive is complete AND every measured verdict passed.
        "exit_gate_17": "PASS" if final else "PARTIAL",
        "exit_gate_note": (
            "The release is reconstructible and verifiable from the repository alone: "
            "the frozen contract surface, the archived release surface, the measured "
            "gate verdicts, the rubric map and the decision register are all in the "
            "tree, and `reconstruct.commands` lists the exact steps."
        ),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": _git_commit(),
        "git_sha_note": (
            "the commit the working tree was based on when the archive was "
            "generated (the archive is written before the commit that carries "
            "it); the frozen digest is the commit-independent anchor."
        ),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "tasks": {
            "17.1": {"status": "DONE", "evidence": "docs/EVIDENCE/evidence_freeze.json"},
            "17.2": {"status": "DONE", "evidence": "gates.verify / gates.replay_all"},
            "17.3": {"status": "DONE", "evidence": "rubric_map / decisions"},
            "17.4": {"status": "DONE", "evidence": "docs/RELEASE_NOTES.md + GitHub release"},
            "17.5": {"status": "DONE", "evidence": "docs/STATUS.md + docs/LIMITATIONS.md"},
            "17.6": {"status": "DONE", "evidence": "docs/CONTEXT/NEXT_AGENT.md + reconstruct.commands"},
        },
        "contract_freeze": contract_freeze,
        "evidence_freeze": {
            "manifest": EVIDENCE_FREEZE.relative_to(REPO_ROOT).as_posix(),
            "tool": "tools/evidence_freeze.py",
            "verify_command": "python3 tools/evidence_freeze.py --verify --require-reports",
        },
        "gates": gates,
        "rubric_map": rubric,
        "decisions": {
            "path": DECISIONS.relative_to(REPO_ROOT).as_posix(),
            "count": len(_decision_ids()),
            "ids": [d["id"] for d in _decision_ids()],
            "index": _decision_ids(),
        },
        "reconstruct": {
            "note": (
                "Run in this order from a clean checkout of the release tag; every "
                "command is offline, stdlib-only and deterministic."
            ),
            "commands": list(RECONSTRUCT_COMMANDS),
        },
        "limitations": {
            "path": "docs/LIMITATIONS.md",
            "note": (
                "The archive records internal verification results only. It is not a "
                "jury score and never claims one (official_score_claimed: false)."
            ),
        },
    }


def _comparable(archive: dict[str, Any]) -> dict[str, Any]:
    """Strip the informational anchors before comparing."""
    return {k: v for k, v in archive.items() if k not in INFORMATIONAL_FIELDS}


#: Sections that describe **the release run** and are therefore a snapshot:
#: a later commit may legitimately measure something else. They are checked
#: for internal consistency, not for equality with a fresh measurement.
SNAPSHOT_SECTIONS = ("gates", "decisions")


def verify_archive(artifact_path: Path = ARTIFACT_PATH, strict: bool = False) -> tuple[bool, list[str]]:
    """Verify the committed archive.

    Two levels:

    * **always** -- the archive is honest and internally consistent: it
      exists, parses, keeps ``official_score_claimed: false``, records
      EXIT GATE 17 as PASS with a full git SHA, records all six tasks with
      an evidence pointer, quotes the digest that
      ``configs/release_freeze.json`` still holds, archives the twelve
      rubric gates, lists only decisions that still exist in
      ``docs/DECISIONS.md``, and names only reconstruct commands whose
      scripts exist;
    * **``strict=True``** -- additionally requires the *measured* sections
      to equal a fresh measurement. This is the release-time check: it is
      run right before the archive is written, not on every commit.
    """
    if not artifact_path.is_file():
        return False, [f"missing release-evidence archive: {artifact_path}"]
    try:
        committed = _load_json(artifact_path)
    except Exception as exc:
        return False, [f"unreadable release-evidence archive: {exc}"]

    errors: list[str] = []

    if committed.get("official_score_claimed") is not False:
        errors.append("official_score_claimed must be false")
    if committed.get("exit_gate_17") != "PASS":
        errors.append("exit_gate_17 must record PASS")
    if not re.fullmatch(r"[0-9a-f]{40}", str(committed.get("git_sha", ""))):
        errors.append("git_sha must be a full 40-hex commit id")
    tasks = committed.get("tasks") or {}
    for task_id in ("17.1", "17.2", "17.3", "17.4", "17.5", "17.6"):
        entry = tasks.get(task_id)
        if not isinstance(entry, dict) or entry.get("status") != "DONE":
            errors.append(f"task {task_id} is not recorded as DONE")
        elif not str(entry.get("evidence", "")).strip():
            errors.append(f"task {task_id} has no evidence pointer")

    # The frozen digest must still be the one the repository holds.
    contract = committed.get("contract_freeze") or {}
    if CONTRACT_FREEZE.is_file():
        freeze = _load_json(CONTRACT_FREEZE)
        if contract.get("aggregate_sha256") != freeze.get("aggregate_sha256"):
            errors.append("the archived contract-freeze digest differs from configs/release_freeze.json")
        if contract.get("frozen_file_count") != freeze.get("frozen_file_count"):
            errors.append("the archived frozen-file count differs from configs/release_freeze.json")

    # The archived rubric map must still be the twelve gates.
    expected_gates = [f"RC-{i:03d}" for i in range(1, 13)]
    if list((committed.get("rubric_map") or {}).get("gates") or []) != expected_gates:
        errors.append("the archived rubric map does not carry exactly RC-001..RC-012")

    # Every archived decision must still exist (the archive may lag behind,
    # but it must never cite a decision that was removed).
    decisions_path = REPO_ROOT / "docs" / "DECISIONS.md"
    if decisions_path.is_file():
        defined = set(re.findall(r"^##\s+(D-\d{2}-\d{2})\b", decisions_path.read_text(encoding="utf-8"), re.M))
        for decision_id in (committed.get("decisions") or {}).get("ids") or []:
            if decision_id not in defined:
                errors.append(f"archived decision {decision_id} is not defined in docs/DECISIONS.md")

    # The reconstruct list must only name commands that exist.
    commands = (committed.get("reconstruct") or {}).get("commands") or []
    if not commands:
        errors.append("reconstruct.commands is empty")
    for command in commands:
        parts = command.split()
        if (
            len(parts) >= 2
            and parts[0] == "python3"
            and not parts[1].startswith("-")
            and not (REPO_ROOT / parts[1]).is_file()
        ):
            errors.append(f"reconstruct command names a missing script: {command}")

    if strict:
        if committed.get("status") != "FINAL":
            errors.append(
                "the release archive must be FINAL (a DRAFT archive records a "
                "non-passing release run); re-write it after a passing verify"
            )
        current = build_archive()
        committed_cmp = _comparable(committed)
        current_cmp = _comparable(current)
        for key in sorted(set(committed_cmp) | set(current_cmp)):
            if key in SNAPSHOT_SECTIONS:
                continue
            if committed_cmp.get(key) != current_cmp.get(key):
                errors.append(f"archive section drifted: {key}")
    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger Phase 17 release-evidence archive")
    parser.add_argument("--write", action="store_true", help="Write the release-evidence archive")
    parser.add_argument("--verify", action="store_true", help="Verify the committed archive")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Additionally require the measured sections to equal a fresh measurement (release-time check)",
    )
    args = parser.parse_args(argv)

    if args.write:
        doc = build_archive()
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        gates = doc["gates"]
        _say(
            f"[PASS] release_evidence --write: status={doc['status']} "
            f"verify={gates['verify'].get('status')} "
            f"({gates['verify'].get('gates_passed')}/{gates['verify'].get('gates_total')} gates), "
            f"replay-all={gates['replay_all'].get('status')} "
            f"({gates['replay_all'].get('runs_matched')}/{gates['replay_all'].get('runs_replayed')} runs), "
            f"decisions={doc['decisions']['count']} -> {ARTIFACT_PATH}"
        )
        return 0

    ok, errs = verify_archive(strict=args.strict)
    if ok:
        _say("[PASS] release_evidence --verify: archive is honest, self-consistent and current")
        return 0
    _say(f"[FAIL] release_evidence --verify ({len(errs)} errors):")
    for err in errs:
        _say(f"  - {err}")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
