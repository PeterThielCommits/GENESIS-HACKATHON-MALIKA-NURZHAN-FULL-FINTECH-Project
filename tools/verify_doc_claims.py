#!/usr/bin/env python3
"""Documentation claim verifier (Phase 15, tasks 15.5 & 15.6; TZ §24).

Makes TZ 15.6 ("no unsupported claims or fake metrics") a machine check rather
than a reviewer's opinion.

Three mechanisms, all read-only unless ``--write`` is passed:

1. **Generated facts block.** ``README.md`` contains a delimited section
   (``<!-- BEGIN GENERATED:measured-facts -->`` … ``<!-- END … -->``) that is
   rendered *from measured artifacts*. Check mode requires it to match the
   freshly rendered text byte-for-byte, so a stale number fails the gate.
   ``--write`` refreshes it (the only documented way to update those values).

2. **Prose assertions.** Counts that appear in hand-written sentences
   ("410 tests", "12/12 PASS", "5/5 byte-identical replays", …) must be present
   with the *current* measured value.

3. **Stale-literal denylist.** Values that were once published and are now
   known-wrong (e.g. ``317 tests``, ``9 encoding transforms (exact``, the
   ``Replay Suite: 0/0`` bug) must never reappear anywhere in the docs.

Stdlib only, offline, deterministic (no timings or wall-clock values are
asserted; durations are rendered with an explicit "sample" caveat).

Usage:
  python3 tools/verify_doc_claims.py            # check (exit 0 = all claims hold)
  python3 tools/verify_doc_claims.py --write    # refresh the generated block
  python3 tools/verify_doc_claims.py --json     # machine-readable report
  python3 tools/verify_doc_claims.py --list     # list measured facts
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"
TRAJECTORY_LOG = REPO_ROOT / "artifacts" / "trajectories" / "trajectories.jsonl"
# NOTE: deliberately NOT inside ``artifacts/reports/latest/``. That directory is
# the frozen Judge Kit evidence set (TZ §23.5, exactly 21 files, 12 gates).
# Adding a file there would make the artifact count depend on whether `make
# docs-verify` ran before or after `make verify`, i.e. non-deterministic
# documentation. This report is a Phase 15 documentation artefact and lives in
# its own directory.
OUTPUT_PATH = REPO_ROOT / "artifacts" / "reports" / "doc_claims" / "doc_claims_report.json"

README = "README.md"
BEGIN_MARK = "<!-- BEGIN GENERATED:measured-facts -->"
END_MARK = "<!-- END GENERATED:measured-facts -->"

# Documentation that must never re-introduce a known-wrong published value.
DOC_SCAN: tuple[str, ...] = (
    "README.md",
    "docs/LIMITATIONS.md",
    "docs/THREAT_MODEL.md",
    "docs/DESIGN.md",
    "docs/INDEPENDENCE.md",
    "docs/DATA_DICTIONARY.md",
    "docs/API_USAGE.md",
    "docs/POLICY_PROTOCOL.md",
    "docs/RUBRIC_TRACEABILITY.md",
    "docs/OFFICIAL_COMPLIANCE_MATRIX.md",
    "docs/DEMO.md",
)


# --------------------------------------------------------------------------- #
# measurement helpers — every value originates in an artifact or frozen contract
# --------------------------------------------------------------------------- #
def _load(name: str) -> dict[str, Any]:
    path = REPORT_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"{name} missing — run `make verify` first (claims are measured from artifacts)")
    return json.loads(path.read_text(encoding="utf-8"))


def _deep(name: str, *keys: str) -> Any:
    node: Any = _load(name)
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"{name}: missing key path {'.'.join(keys)}")
        node = node[key]
    return node


def _verify_summary() -> dict[str, Any]:
    return _load("verify_summary.json")


def _count_from_check(check_id: str) -> int:
    for check in _verify_summary().get("checks", []):
        if check.get("check_id") == check_id:
            found = re.findall(r"Ran (\d+) tests", check.get("output_tail", ""))
            if found:
                return int(found[-1])
    raise KeyError(f"verify_summary.json: {check_id} output_tail has no 'Ran N tests'")


def _trajectory_stats(policy: str) -> dict[str, Any]:
    if not TRAJECTORY_LOG.is_file():
        raise FileNotFoundError("artifacts/trajectories/trajectories.jsonl missing — run `make official-eval`")
    rows = [
        json.loads(line)
        for line in TRAJECTORY_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows = [r for r in rows if r.get("policy") == policy]
    if not rows:
        raise KeyError(f"trajectories.jsonl: no rows for policy {policy!r}")
    f1 = [r["metrics"]["f1"] for r in rows if r.get("metrics", {}).get("f1") is not None]
    ret = [r["metrics"]["return"] for r in rows if r.get("metrics", {}).get("return") is not None]
    steps = [r["inspection_steps"] for r in rows if r.get("inspection_steps") is not None]
    dur = [r["duration_s"] for r in rows if r.get("duration_s") is not None]
    return {
        "episodes": len(rows),
        "f1": statistics.mean(f1),
        "return": statistics.mean(ret),
        "steps": statistics.mean(steps),
        "max_duration": max(dur),
    }


def _tool_enum() -> list[str]:
    schema = json.loads((REPO_ROOT / "contracts" / "tool_request.schema.json").read_text(encoding="utf-8"))
    return list(schema["properties"]["action"]["properties"]["tool"]["enum"])


def _error_enum() -> list[str]:
    schema = json.loads((REPO_ROOT / "contracts" / "tool_response.schema.json").read_text(encoding="utf-8"))
    return list(schema["properties"]["error"]["properties"]["code"]["enum"])


def _src() -> tuple[list[str], list[str]]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from judge.canary_fuzzer import ENCODING_TRANSFORMS, POLICY_VISIBLE_CHANNELS

    return list(POLICY_VISIBLE_CHANNELS), list(ENCODING_TRANSFORMS)


# --------------------------------------------------------------------------- #
# measured facts — the single source for every published number
# --------------------------------------------------------------------------- #
def collect_facts() -> list[dict[str, str]]:
    """Return ordered (id, label, value, source) facts rendered into the README."""
    summary = _verify_summary()
    checks = summary.get("checks", [])
    gates_total = len(checks)
    index = _load("report_index.json")
    channels, transforms = _src()
    facts: list[dict[str, str]] = [
        # NOTE: the gate pass-ratio and overall status are deliberately NOT
        # published as asserted facts. They are produced by the very run that
        # executes this check, so asserting them is circular: a run that fails
        # *because of doc drift* writes a failing summary, which then makes the
        # next run's expected wording differ again (a deadlock). Outcome-independent
        # counts are published instead; the verdict itself is carried by the
        # process exit code and verify_summary.json.
        {
            "id": "F-GATES",
            "label": "Verification gates defined (RC-001..RC-012)",
            "value": str(gates_total),
            "source": "verify_summary.json",
        },
        {
            "id": "F-OFFICIAL-SCORE-CLAIM",
            "label": "Official organiser score claimed",
            "value": str(summary.get("official_score_claimed")).lower(),
            "source": "verify_summary.json",
        },
        {
            "id": "F-TESTS",
            "label": "Total tests in the verification suite",
            "value": str(_count_from_check("RC-001")),
            "source": "verify_summary.json → RC-001",
        },
        {
            "id": "F-TESTS-OFFICIAL",
            "label": "Official mirror tests (Blocks 1–5)",
            "value": str(_count_from_check("RC-004")),
            "source": "verify_summary.json → RC-004",
        },
        {
            "id": "F-ARTIFACTS",
            "label": "Evidence artifacts indexed",
            "value": str(len(index.get("artifacts", []))),
            "source": "report_index.json",
        },
        {
            "id": "F-ARTIFACTS-MISSING",
            "label": "Required artifacts missing",
            "value": str(len(index.get("missing_optional_or_full_mode_artifacts", []))),
            "source": "report_index.json",
        },
        {
            "id": "F-REPLAY",
            "label": "Byte-identical fresh-process replays",
            "value": f"{_deep('replay_report.json', 'episodes_matched')}/{_deep('replay_report.json', 'episodes_tested')}",
            "source": "replay_report.json",
        },
        {
            "id": "F-MUTANTS",
            "label": "Mutants killed",
            "value": str(_deep("mutation_test_report.json", "summary", "mutation_score_exact")),
            "source": "mutation_test_report.json",
        },
        {
            "id": "F-METAMORPHIC",
            "label": "Metamorphic transforms passed",
            "value": (
                f"{_deep('metamorphic_report.json', 'summary', 'transforms_passed')}"
                f"/{_deep('metamorphic_report.json', 'summary', 'transforms_total')}"
            ),
            "source": "metamorphic_report.json",
        },
        {
            "id": "F-ROBUSTNESS-PAIRS",
            "label": "Prompt-injection twin pairs evaluated",
            "value": str(_deep("robustness_report.json", "summary", "pairs_evaluated")),
            "source": "robustness_report.json",
        },
        {
            "id": "F-INVARIANTS",
            "label": "Invariant catalog (TZ §12.1)",
            "value": f"INV-01..INV-{int(_deep('invariants_report.json', 'invariants_catalog_count')):02d}",
            "source": "invariants_report.json",
        },
        {
            "id": "F-CANARY-HITS",
            "label": "Canary leakage hits",
            "value": str(_deep("canary_fuzz_report.json", "canary_summary", "total_canary_hits")),
            "source": "canary_fuzz_report.json",
        },
        {
            "id": "F-CANARY-CHANNELS",
            "label": "Policy-visible canary channels",
            "value": str(len(channels)),
            "source": "judge/canary_fuzzer.py",
        },
        {
            "id": "F-ENCODING-TRANSFORMS",
            "label": "Canary encoding transforms",
            "value": str(len(transforms)),
            "source": "judge/canary_fuzzer.py",
        },
        {
            "id": "F-SHORTCUT-AUC",
            "label": "Shortcut macro ROC AUC (limit 0.55)",
            "value": str(_deep("shortcut_audit.json", "metadata_classifier", "macro_roc_auc")),
            "source": "shortcut_audit.json",
        },
        # Budgets, not samples: env-step latency and RSS measurements vary run to
        # run, so publishing them as byte-compared documentation would make the
        # gate fail spuriously. What is stable is the declared budget and the
        # PASS/FAIL verdict of the gate that enforces it.
        {
            "id": "F-PERF-BUDGETS",
            "label": "Performance budgets (step p99 / RSS / episode disk)",
            "value": (
                f"< {_deep('performance_report.json', 'metrics', 'target_env_step_p99_ms_lt')} ms / "
                f"< {_deep('performance_report.json', 'metrics', 'target_peak_rss_mb_lt')} MB / "
                f"< {_deep('performance_report.json', 'metrics', 'target_episode_disk_mb_lt')} MB"
            ),
            "source": "performance_report.json",
        },
        {
            "id": "F-PERF-VERDICT",
            "label": "Performance & dependency gate",
            "value": str(_deep("performance_report.json", "status")),
            "source": "performance_report.json",
        },
        # A "latest measured latency" row is intentionally absent: any sampled
        # timing value inside a byte-compared block makes the gate fail on the
        # next verify run. Read performance_report.json directly for the sample;
        # the stable, asserted facts are the budgets and the verdict above.
        {
            "id": "F-STDLIB",
            "label": "Core stdlib-only",
            "value": str(_deep("dependency_report.json", "core_stdlib_only")).lower(),
            "source": "dependency_report.json",
        },
        {
            "id": "F-NETWORK",
            "label": "Runtime network required",
            "value": str(_deep("dependency_report.json", "runtime_network_required")).lower(),
            "source": "dependency_report.json",
        },
        {
            "id": "F-TOOLS",
            "label": "Core JSONL protocol tools",
            "value": ", ".join(f"`{t}`" for t in _tool_enum()),
            "source": "contracts/tool_request.schema.json",
        },
        {
            "id": "F-ERRORS",
            "label": "Bounded tool error codes",
            "value": str(len(_error_enum())),
            "source": "contracts/tool_response.schema.json",
        },
        {
            "id": "F-DEMO-SEED",
            "label": "Demo walkthrough seed",
            "value": "2025",
            "source": "tools/demo_walkthrough.py",
        },
    ]
    return facts


BASELINE_POLICIES: tuple[tuple[str, str], ...] = (
    ("oracle", "Judge-side reference"),
    ("simple_reconciliation", "OS subprocess worker"),
    ("random", "OS subprocess worker"),
    ("mass_flagging", "OS subprocess worker"),
)


def render_block() -> str:
    """Render the generated facts block (markdown), deterministically."""
    lines = [
        BEGIN_MARK,
        "<!-- Generated by `python3 tools/verify_doc_claims.py --write`. Do not edit by hand:",
        "     `make verify` / CI fails if this block disagrees with the measured artifacts. -->",
        "",
        "### Measured Facts (auto-generated)",
        "",
        "| Fact | Value | Source artifact |",
        "|---|---|---|",
    ]
    for fact in collect_facts():
        lines.append(f"| {fact['label']} | **{fact['value']}** | `{fact['source']}` |")

    lines += [
        "",
        "### Measured Baselines — D01..D20, seed 2026 (auto-generated)",
        "",
        "| Policy | Isolation | Mean F1 | Mean Return | Mean Steps | Episodes |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for policy, isolation in BASELINE_POLICIES:
        s = _trajectory_stats(policy)
        # Wall-clock duration is a sample, not a deterministic property: it is
        # deliberately excluded so documentation cannot drift on timing noise.
        lines.append(
            f"| `{policy}` | {isolation} | {s['f1']:.4f} | {s['return']:+.4f} | "
            f"{s['steps']:.1f} | {s['episodes']} |"
        )
    lines += [
        "",
        "Source: `artifacts/trajectories/trajectories.jsonl` (80 episode rows). "
        "Reproduce with `make official-eval`.",
        END_MARK,
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# prose assertions & stale-literal denylist
# --------------------------------------------------------------------------- #
def prose_assertions() -> list[dict[str, str]]:
    """Counts stated in hand-written prose that must track the measurement."""
    summary = _verify_summary()
    checks = summary.get("checks", [])
    gates_total = len(checks)
    channels, transforms = _src()
    return [
        {
            "id": "P-GATES",
            "doc": "README.md",
            "needle": f"{gates_total}-gate Judge Kit",
            "why": "verify gate summary (outcome-independent)",
        },
        {
            "id": "P-TESTS",
            "doc": "README.md",
            "needle": f"{_count_from_check('RC-001')} tests",
            "why": "test count in the command block",
        },
        {
            "id": "P-REPLAY",
            "doc": "README.md",
            "needle": f"{_deep('replay_report.json', 'episodes_matched')}/{_deep('replay_report.json', 'episodes_tested')} byte-identical replays",
            "why": "replay claim",
        },
        {
            "id": "P-CHANNELS",
            "doc": "docs/LIMITATIONS.md",
            "needle": f"{len(channels)}-channel canary",
            "why": "canary channel count",
        },
        {
            "id": "P-TRANSFORMS",
            "doc": "docs/LIMITATIONS.md",
            "needle": f"{len(transforms)} encoding transforms",
            "why": "canary transform count",
        },
        {
            "id": "P-PROTOCOL-TOOLS",
            "doc": "docs/POLICY_PROTOCOL.md",
            "needle": "`" + "`, `".join(_tool_enum()) + "`",
            "why": "protocol tool enum",
        },
        {
            "id": "P-PROTOCOL-ERRORS",
            "doc": "docs/POLICY_PROTOCOL.md",
            "needle": "`" + "`, `".join(_error_enum()) + "`",
            "why": "protocol error enum",
        },
        {
            "id": "P-API-CALC",
            "doc": "docs/API_USAGE.md",
            "needle": "`calculator`",
            "why": "adapter calculator tool name",
        },
    ]


def decision_id_check() -> list[dict[str, str]]:
    """Every ``D-XX-YY`` cited in the docs must exist in docs/DECISIONS.md.

    Guards against phantom decision IDs: a citation to a decision that was never
    recorded is an unsupported claim (TZ 15.6) even when the prose is plausible.
    """
    decisions_path = REPO_ROOT / "docs" / "DECISIONS.md"
    if not decisions_path.is_file():
        return [{"id": "R-DECISIONS", "status": "DOC_MISSING", "detail": "docs/DECISIONS.md not found"}]
    defined = set(re.findall(r"^##\s+(D-\d{2}-\d{2})", decisions_path.read_text(encoding="utf-8"), re.MULTILINE))
    failures: list[dict[str, str]] = []
    for rel in DOC_SCAN:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        for cited in sorted(set(re.findall(r"\bD-\d{2}-\d{2}\b", doc_path.read_text(encoding="utf-8")))):
            if cited not in defined:
                failures.append(
                    {
                        "id": "R-DECISION-ID",
                        "status": "PHANTOM_ID",
                        "doc": rel,
                        "detail": f"{rel} cites {cited}, which is not defined in docs/DECISIONS.md",
                    }
                )
    return failures


# Values that were published once and proven wrong or misleading.
STALE_LITERALS: tuple[tuple[str, str], ...] = (
    ("317 tests", "superseded test count (measured value is in the facts block)"),
    ("317 unit/official/security", "superseded test count"),
    ("9 encoding transforms (`exact`", "transform list did not match the 9 real transforms"),
    ("Replay Suite: 0/0", "replay metrics bug — real value is 5/5"),
    ("is hardcoded to 15", "invariant catalog is INV-01..INV-17"),
    ("15 invariants", "invariant catalog is INV-01..INV-17"),
    ("POLIICY_PROTOCOL", "typo for POLICY_PROTOCOL.md"),
)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify documentation claims against measured artifacts")
    parser.add_argument("--write", action="store_true", help="refresh the generated facts block in README.md")
    parser.add_argument("--json", action="store_true", help="emit the full report to stdout")
    parser.add_argument("--list", action="store_true", help="list measured facts without checking")
    args = parser.parse_args(argv)

    if args.list:
        for fact in collect_facts():
            print(f"{fact['id']:22s} {fact['value']:24s} {fact['source']}")
        print(f"\n{len(collect_facts())} measured facts")
        return 0

    failures: list[dict[str, str]] = []
    checks: list[dict[str, str]] = []
    rendered = render_block()

    readme_path = REPO_ROOT / README
    readme = readme_path.read_text(encoding="utf-8")

    # 1) generated block must exist and match exactly
    if BEGIN_MARK not in readme or END_MARK not in readme:
        if args.write:
            readme = readme.rstrip("\n") + "\n\n" + rendered + "\n"
            readme_path.write_text(readme, encoding="utf-8")
            checks.append({"id": "G-BLOCK", "status": "WRITTEN", "detail": "facts block inserted"})
        else:
            failures.append(
                {
                    "id": "G-BLOCK",
                    "status": "MISSING",
                    "detail": f"README.md has no generated facts block ({BEGIN_MARK}); run --write",
                }
            )
    else:
        start = readme.index(BEGIN_MARK)
        end = readme.index(END_MARK) + len(END_MARK)
        current = readme[start:end]
        if current != rendered:
            if args.write:
                readme_path.write_text(readme[:start] + rendered + readme[end:], encoding="utf-8")
                checks.append({"id": "G-BLOCK", "status": "REFRESHED", "detail": "facts block updated"})
            else:
                failures.append(
                    {
                        "id": "G-BLOCK",
                        "status": "DRIFT",
                        "detail": "generated facts block disagrees with measured artifacts; run --write after checking",
                    }
                )
        else:
            checks.append({"id": "G-BLOCK", "status": "PASS", "detail": "facts block matches measurement"})

    readme = readme_path.read_text(encoding="utf-8")

    # 2) prose assertions
    for assertion in prose_assertions():
        doc_path = REPO_ROOT / assertion["doc"]
        if not doc_path.is_file():
            failures.append({**assertion, "status": "DOC_MISSING", "detail": f"{assertion['doc']} not found"})
            continue
        text = doc_path.read_text(encoding="utf-8")
        if assertion["needle"] in text:
            checks.append({"id": assertion["id"], "status": "PASS", "detail": assertion["needle"]})
        else:
            failures.append(
                {
                    **assertion,
                    "status": "STALE",
                    "detail": f"{assertion['doc']} lacks {assertion['needle']!r} ({assertion['why']})",
                }
            )

    # 3) stale-literal denylist across all jury-facing docs
    for rel in DOC_SCAN:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            failures.append({"id": f"D-MISSING-{rel}", "status": "DOC_MISSING", "detail": f"{rel} not found"})
            continue
        text = doc_path.read_text(encoding="utf-8")
        for literal, reason in STALE_LITERALS:
            if literal in text:
                failures.append(
                    {
                        "id": "D-STALE",
                        "status": "STALE_LITERAL",
                        "doc": rel,
                        "detail": f"{rel} contains superseded literal {literal!r} — {reason}",
                    }
                )
    checks.append({"id": "D-DENYLIST", "status": "PASS", "detail": f"{len(DOC_SCAN)} docs scanned for stale literals"})

    # 4) referential integrity of cited decision IDs
    decision_failures = decision_id_check()
    failures.extend(decision_failures)
    if not decision_failures:
        checks.append({"id": "R-DECISIONS", "status": "PASS", "detail": "all cited decision IDs exist"})

    status = "PASS" if not failures else "FAIL"
    report = {
        "schema_version": "1.0.0",
        "report_type": "doc_claims_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": "",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "command": "python3 tools/verify_doc_claims.py",
        "status": status,
        "facts_total": len(collect_facts()),
        "checks_passed": sum(1 for c in checks if c["status"] in ("PASS", "WRITTEN", "REFRESHED")),
        "failures": failures,
        "facts": collect_facts(),
        "checks": checks,
    }

    from contracts.canonical import sha256_hex

    report["config_hash"] = sha256_hex(
        {"facts": [f["id"] for f in report["facts"]], "docs": list(DOC_SCAN)}
    )
    # The report is a convenience artifact, not the verdict: the verdict is the
    # exit code. Under a read-only rootfs (hardened offline container, TZ §22.4)
    # writing may be impossible unless a tmpfs is mounted, and that must never
    # turn a passing documentation check into a crash.
    report_written = True
    try:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        report_written = False
        print(f"doc-claims: note: report not written ({exc.__class__.__name__}: {exc}); verdict still authoritative")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"doc-claims: {status} ({report['facts_total']} measured facts, {report['checks_passed']} checks passed)")
        if args.write:
            print(f"  generated block refreshed in {README}")
        for failure in failures:
            print(f"  [{failure['status']}] {failure['id']}: {failure.get('detail', '')}")
        if report_written:
            try:
                shown = OUTPUT_PATH.relative_to(REPO_ROOT)
            except ValueError:  # caller redirected the output outside the repo
                shown = OUTPUT_PATH
            print(f"report: {shown}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
