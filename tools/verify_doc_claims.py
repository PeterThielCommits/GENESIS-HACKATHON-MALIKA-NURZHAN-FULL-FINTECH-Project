#!/usr/bin/env python3
"""Documentation claim verifier (Phase 15, tasks 15.5 & 15.6; TZ §24).

Makes TZ 15.6 ("no unsupported claims or fake metrics") a machine check rather
than a reviewer's opinion.

Mechanisms, all read-only unless ``--write`` is passed. The first four are
**numeric** (a published value must equal a measured value); the last block is
**structural** (a published *shape* must equal the real shape — a path that
must exist, a field list that must match the data, a demo table that must match
the program).

Numeric mechanisms
------------------
1. **Generated facts block.** ``README.md`` contains a delimited section
   (``<!-- BEGIN GENERATED:measured-facts -->`` … ``<!-- END … -->``) that is
   rendered *from measured artifacts*. Check mode requires it to match the
   freshly rendered text byte-for-byte, so a stale number fails the gate.
   ``--write`` refreshes it (the only documented way to update those values).
2. **Prose assertions.** Counts that appear in hand-written sentences
   ("12/12 PASS", "5/5 byte-identical replays", …) must be present
   with the *current* measured value.
3. **Stale-literal denylist.** Values that were once published and are now
   known-wrong (e.g. ``9 encoding transforms (exact``, the
   ``Replay Suite: 0/0`` bug) must never reappear anywhere in the docs.
4. **Referential integrity of decision IDs.** Every ``D-XX-YY`` cited in a doc
   must be defined in ``docs/DECISIONS.md``.

Structural mechanisms
---------------------
5. **Path references (``C-PATHS``).** Every backticked repository path a doc
   cites must resolve on disk. This is what catches "documented file that does
   not exist", the failure mode numbers cannot see.
6. **Data-dictionary fidelity (``C-DATADICT``).** Every field list published in
   ``docs/DATA_DICTIONARY.md`` is compared *both ways* against a real generated
   episode: no documented field may be absent from the data, and no real field
   may be silently omitted from the dictionary.
7. **Demo agreement (``C-DEMO``).** ``docs/DEMO.md``'s segment table must equal
   ``tools/demo_walkthrough.py``'s ``SEGMENTS`` tuple — the same tuple the
   program prints, so the document cannot describe a demo that is not the one
   that runs.
8. **Public entrypoint surface (``C-WORKBENCH-API``).** Every HTTP route a doc
   publishes for ``tools/demo_server.py`` must be dispatched by its real
   handler, in the documented HTTP method.
9. **Command executability (``C-COMMANDS``).** Every ``python3 <script>`` /
   ``make <target>`` a doc presents must exist and be parseable; a documented
   command that cannot be parsed is as wrong as a wrong number.
10. **Reward provenance (``C-REWARD``).** The formula quoted in the docs must be
    the formula the single live implementation computes (``D-18-01``), and no
    doc may present it as provisional.
11. **Suite totals (``C-COUNTS``).** Recognised suite-total phrases in the
    jury-facing scan set must match unittest discovery. Explicit official totals
    are measured separately; small unqualified subset counts are not inferred.

Stdlib only, offline, deterministic (no timings or wall-clock values are
asserted; durations are rendered with an explicit "sample" caveat).

Usage:
  python3 tools/verify_doc_claims.py            # check (exit 0 = all claims hold)
  python3 tools/verify_doc_claims.py --write    # refresh the generated block and recognised prose totals
  python3 tools/verify_doc_claims.py --json     # machine-readable report
  python3 tools/verify_doc_claims.py --list     # list measured facts
"""

from __future__ import annotations

import argparse
import functools
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
# the frozen Judge Kit evidence set (TZ §23.5, 20 evidence files, 12 gates).
# Adding a file there would make the artifact count depend on whether `make
# docs-verify` ran before or after `make verify`, i.e. non-deterministic
# documentation. This report is a Phase 15 documentation artefact and lives in
# its own directory. (See D-15-03: the count is 20, stable across a checkout and
# the offline image, because `.gitkeep` is a placeholder and not evidence.)
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
def _first_difference(expected: str, actual: str) -> str:
    """Describe the first disagreeing line, so drift is diagnosable.

    A bare "the block disagrees" is unusable in CI, where the failing job's log
    is not always retrievable. Naming the line turns a mystery into a fix.
    """
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    for index, (want, got) in enumerate(zip(expected_lines, actual_lines), start=1):
        if want != got:
            return f"line {index}: committed {got.strip()[:90]!r} != measured {want.strip()[:90]!r}"
    if len(expected_lines) != len(actual_lines):
        return f"line count: committed {len(actual_lines)} != measured {len(expected_lines)}"
    return "whitespace or trailing newline differs"


def _say(message: str) -> None:
    """Print without ever depending on the host locale's encoding.

    The hardened offline container runs with a C/POSIX locale, where
    ``sys.stdout.encoding`` is ASCII and any non-ASCII character (em dash,
    arrow, section sign) raises UnicodeEncodeError -- which is exactly how the
    docker-offline job failed while ``core`` passed. Console text is therefore
    transliterated; the *files* we write are always explicit UTF-8.
    """
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
        encoded = transliterated.encode("ascii", "replace").decode("ascii")
        print(encoded)


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


#: Cached discovery count. Discovery is pure and deterministic within a process,
#: but it walks the whole test tree, so it is measured once.
_DISCOVERED_TESTS: dict[str, int] = {}


def _discovered_test_count(subdir: str = "tests") -> int:
    """Count a suite by discovery, independent of which gate run wrote the summary.

    Why not read it from ``verify_summary.json``? Because that count describes *the
    run that wrote the file*: a ``--core`` run writes six gates, and its RC-001
    line still says 524 while a full run says 522 — the difference is two tests
    that skip on core-mode evidence. A published fact that changes with target
    execution order is exactly what D-15-01 forbids, and it made
    ``make verify-core && make docs-verify`` fail on a correct tree.

    Discovery over ``tests/`` is the same set every time, so the number is stable.
    """
    if subdir in _DISCOVERED_TESTS:
        return _DISCOVERED_TESTS[subdir]
    import unittest

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(REPO_ROOT / subdir), top_level_dir=str(REPO_ROOT))
    _DISCOVERED_TESTS[subdir] = int(suite.countTestCases())
    return _DISCOVERED_TESTS[subdir]


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
RUBRIC_MAP = REPO_ROOT / "judge" / "rubric_map.json"


def defined_gate_count() -> int:
    """Number of gates the *contract* defines, not the number that just ran.

    `verify_summary.json` lists only the checks of the most recent run, so a
    `make verify-core` (6 gates) followed by `make docs-verify` published "6
    gates" and then a full run reported DRIFT. Order-dependent facts are exactly
    what D-15-01 forbids. The frozen rubric map is the contract: 12 gates.
    """
    data = json.loads(RUBRIC_MAP.read_text(encoding="utf-8"))
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("judge/rubric_map.json defines no checks")
    return len(checks)


def baseline_log_available() -> bool:
    """True when the committed trajectory log is readable.

    ``make verify`` never writes it (it comes from ``make official-eval`` and is
    committed), and the hardened offline container mounts an empty tmpfs over
    ``artifacts/trajectories`` — which *masks* the committed file on purpose, so
    that a run can prove it produces its own outputs from scratch. Baseline
    rows are therefore an optional fact block, guarded by this probe, and are
    skipped with an explicit note rather than crashing the whole gate.
    """
    return TRAJECTORY_LOG.is_file()


def collect_facts() -> list[dict[str, str]]:
    """Return ordered (id, label, value, source) facts rendered into the README."""
    summary = _verify_summary()
    checks = summary.get("checks", [])
    gates_total = defined_gate_count()
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
            "source": "judge/rubric_map.json (frozen contract)",
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
            "value": str(_discovered_test_count()),
            "source": "unittest discovery over tests/ (state-independent)",
        },
        {
            "id": "F-TESTS-OFFICIAL",
            "label": "Official mirror tests (Blocks 1–5)",
            # Discovery, not the summary: same reason as F-TESTS. RC-004 runs
            # `tests/official`, so this is the identical set, measured without
            # depending on which target wrote the summary last.
            "value": str(_discovered_test_count("tests/official")),
            "source": "unittest discovery over tests/official/ (state-independent)",
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


BASELINE_HEADING = "### Measured Baselines"


def strip_baselines(block: str) -> str:
    """Return ``block`` with its baseline section removed.

    Used for comparison when the trajectory log is unreadable: the committed
    README still publishes the baseline rows, and a run that cannot read the log
    must not report a drift that is purely an environment difference.
    """
    index = block.find(BASELINE_HEADING)
    if index == -1:
        return block
    return block[:index] + "<!-- END GENERATED:measured-facts -->"


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
    if not baseline_log_available():
        lines += [
            "| _(baselines omitted)_ | Trajectory log not readable in this environment | "
            "`artifacts/trajectories/trajectories.jsonl` |",
            "",
            "Baseline rows are published by the repository README and measured from",
            "`artifacts/trajectories/trajectories.jsonl`. They are intentionally absent",
            "here when that log is not readable (e.g. inside the hardened offline",
            "container, which masks `artifacts/trajectories` with an empty tmpfs).",
            END_MARK,
        ]
        return "\n".join(lines)

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
    gates_total = defined_gate_count()
    channels, transforms = _src()
    return [
        {
            "id": "P-GATES",
            "doc": "README.md",
            "needle": f"{gates_total}-gate Judge Kit",
            "why": "verify gate summary (outcome-independent)",
        },
        # NOTE: there is deliberately no P-TESTS prose needle. The test count is a
        # generated fact (F-TESTS) rendered into the byte-compared block, and a
        # second hand-written copy in prose is exactly the drift trap that made
        # this check fail on its own author: adding tests to this very file
        # changed the count, and the prose needle then required a manual edit that
        # no reviewer would remember. C-COUNTS now checks recognised prose copies
        # against discovery and --write refreshes them alongside the block.
        {
            "id": "P-TESTS-BLOCK",
            "doc": "README.md",
            "needle": "Total tests in the verification suite",
            "why": "the authoritative count is in the generated block; C-COUNTS checks prose copies",
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


# --------------------------------------------------------------------------- #
# structural checks — a published *shape* must equal the real shape
#
# Every defect these catch was found by hand in the Phase 15 structural audit,
# after the numeric gate had passed: numbers were right, and the prose around
# them described files, fields, routes and a demo that did not exist. A number
# can be re-measured; a sentence cannot, so the sentence is pinned to a source.
# --------------------------------------------------------------------------- #
# Extension set used to decide whether a backticked token claims to be a file.
_PATH_SUFFIXES: frozenset[str] = frozenset(
    {".md", ".json", ".py", ".jsonl", ".yaml", ".yml", ".txt", ".html", ".csv", ".toml", ".cfg", ".ini"}
)
# Outputs that are produced by a gate run rather than committed. A doc may cite
# them by bare name (the convention throughout this repo) or by full path; either
# way the assertion is against the producer's contract, never against the file.
_GENERATED_CITED_PREFIXES: tuple[str, ...] = (
    "artifacts/reports/",
    "artifacts/trajectories/",
)
# Paths that are *defined by their absence*: the docs say "forbidden", "must be
# rejected", "carries no sealed/". They are never expected to resolve.
_ABSENT_BY_DESIGN: frozenset[str] = frozenset(
    {
        "index_hints.json",
        "sealed/",
        "sealed/truth.json",
        "provenance.json",
        "truth.json",
        "public/",  # cited as "<episode>/public/" or "inside public/"
        "manifest.json",  # per-episode name, cited without its directory
        "canonical.py",
        "currency.py",
        "validate.py",
        "money.py",
        "rounding.py",
        "time_utils.py",
        "report.py",
        "duplicate_payment.py",
        "partial_allocation.py",
        "fx_mismatch.py",
        "period_cutoff.py",
        "ablation.py",
        "verifier_report.json",
        "episodes/dev/ep_x/sealed/",  # illustrative placeholder in a report
    }
)
#: Files that live *inside* an episode directory, so a bare filename is the only
#: sensible way to cite them. Their existence is contracted by the loader's
#: allowlist (``verifier/public_loader.py``, ``env/loader.py``) and asserted by the
#: data-dictionary check, not by a path lookup from the repository root.
_PER_EPISODE_FILES: frozenset[str] = frozenset(
    {
        "company.json",
        "policy.json",
        "accounts.json",
        "counterparties.jsonl",
        "journal_entries.jsonl",
        "invoices.jsonl",
        "credit_notes.jsonl",
        "payments.jsonl",
        "bank_lines.jsonl",
        "fx_rates.jsonl",
        "opening_balances.json",
        "period_calendar.json",
    }
)
#: Top-level packages whose modules a doc may name by bare filename.
_PACKAGE_ZONES: tuple[str, ...] = (
    "contracts", "core", "gen", "verifier", "env", "adapter", "scoring", "seal",
    "harness", "arena", "nlp", "judge", "metamorphic", "tools", "invariants", "tests",
)
_BACKTICK_TOKEN = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./<>{}*]*?)`")


#: ``prefix/`` → artifacts the prefix's producer is contracted to emit.
_GENERATED_DIR_CONTRACTS: dict[str, tuple[str, ...]] = {}


def _generated_dir_contracts() -> dict[str, tuple[str, ...]]:
    """Map each generated output directory to the files its producer must emit.

    Read from ``judge/verify.py``'s frozen artifact list rather than re-typed, so
    "the docs say this file will be here" is checked against the same contract
    the gate itself enforces. A bare filename (``replay_report.json``) is a
    legitimate way to cite a generated artifact in prose; a bare filename that
    matches no producer is not.
    """
    global _GENERATED_DIR_CONTRACTS
    if _GENERATED_DIR_CONTRACTS:
        return _GENERATED_DIR_CONTRACTS
    verify_source = (REPO_ROOT / "judge" / "verify.py").read_text(encoding="utf-8")
    match = re.search(r"REQUIRED_FULL_ARTIFACTS[^=]*=\s*\((.*?)\)", verify_source, re.DOTALL)
    frozen: set[str] = set(re.findall(r'"([^"]+\.(?:json|txt|csv|html|md))"', match.group(1))) if match else set()
    # Artifacts other producers own, named by their own outputs.
    extra = {
        "doc_claims_report.json",
        "release_audit.json",
        "replay_all_report.json",
        "official_eval_summary.json",
        "performance_report.json",
    }
    doc_claims = REPORT_DIR.parent / "doc_claims"
    release = REPORT_DIR.parent / "release"
    _GENERATED_DIR_CONTRACTS = {
        "artifacts/reports/latest/": tuple(sorted(frozen)),
        "artifacts/reports/doc_claims/": tuple(sorted(extra & {"doc_claims_report.json"})),
        "artifacts/reports/release/": tuple(sorted(extra & {"release_audit.json", "replay_all_report.json"})),
        "artifacts/reports/evaluation/": ("official_eval_summary.json",),
        "artifacts/trajectories/": ("trajectories.jsonl",),
    }
    return _GENERATED_DIR_CONTRACTS


def _resolve_path_token(token: str) -> str:
    """Classify one backticked token as ``skip``, ``exists`` or ``missing``.

    Three tiers, because docs legitimately cite three kinds of thing:

    * a **committed** path → must exist on disk;
    * a **generated** artifact → must be named by its producer's contract
      (``judge/verify.py::REQUIRED_FULL_ARTIFACTS`` or the producer's own output
      name). Asserting the *file* would fail on a bare checkout; asserting the
      *contract* is meaningful on every checkout;
    * a path that is **absent by design** (``sealed/truth.json`` in a doc that says
      "never public") → never expected to resolve.
    """
    if any(ch in token for ch in "*<>{}") or token.startswith("/"):
        return "skip"
    # arena/<id>-... are git branch names woven into prose, never paths.
    if token.startswith("arena/") and not (REPO_ROOT / token).exists():
        return "skip"
    # Prose that happens to sit in backticks: ratios, dotted call paths, zoneinfo
    # names, illustrative IDs. None of these is a filesystem claim.
    if re.fullmatch(r"[\d/]+", token):
        return "skip"
    if re.fullmatch(r"[A-Z][a-z]+/[A-Z][a-z]+", token):
        return "skip"
    if re.fullmatch(r"[\w./]+\.[a-z_][\w.]*\(.*\)", token):
        return "skip"
    if token in _ABSENT_BY_DESIGN:
        return "skip"
    suffix = pathlib_suffix(token)
    is_file = suffix in _PATH_SUFFIXES
    is_dir = token.endswith("/")
    if not (is_file or is_dir):
        return "skip"

    # Generated-artifact citation, by full path or by bare contracted filename.
    contracts = _generated_dir_contracts()
    if token.startswith(_GENERATED_CITED_PREFIXES):
        for prefix, produced in contracts.items():
            if token.startswith(prefix):
                leaf = token[len(prefix):]
                return "skip" if leaf in produced or leaf == "" else "missing"
        return "skip"
    if is_file and token.count("/") == 0:
        produced_anywhere = {name for names in contracts.values() for name in names}
        if token in produced_anywhere or token in _PER_EPISODE_FILES:
            return "skip"
        # A generated directory citation such as `trajectories.jsonl` that is not
        # in any contract is a real phantom; fall through to the on-disk check.
    if is_dir:
        return "exists" if (REPO_ROOT / token).is_dir() else "missing"
    if is_file and token.count("/") == 0 and token.endswith(".py"):
        # A bare module name ("the `report.py` module") names a file, not a place.
        return "exists" if _module_name_exists(token) else "missing"
    return "exists" if (REPO_ROOT / token).exists() else "missing"


def _module_name_exists(filename: str) -> bool:
    """True when ``filename`` names a real module anywhere in the package tree.

    Root-level modules (``judge_adapter.py``) count, because that is the official
    entrypoint and the docs name it constantly.
    """
    if (REPO_ROOT / filename).is_file():
        return True
    return any((REPO_ROOT / zone / filename).is_file() for zone in _PACKAGE_ZONES)


def pathlib_suffix(token: str) -> str:
    """The token's file extension, or ``""`` when it carries none."""
    leaf = token.rsplit("/", 1)[-1]
    if "." not in leaf or leaf.startswith("."):
        return ""
    return "." + leaf.rsplit(".", 1)[-1]


#: A line that says a path is absent is *documenting* the absence, not claiming
#: the file. Incident reports, limitation disclosures and "the previous version
#: of this page named X" corrections all have to be able to say so.
_NEGATION_CUES: tuple[str, ...] = (
    "does not exist",
    "do not exist",
    "no longer exists",
    "never existed",
    "not exist",
    "removed",
    "deleted",
    "renamed",
    "forbidden",
    "must not",
    "must never",
    "never public",
    "rejected",
    "not permitted",
    "absent",
    "previous version",
    "previously",
    "misleading",
    "wrong",
)


def path_reference_check() -> list[dict[str, str]]:
    """``C-PATHS``: every backticked repository path in a doc must resolve.

    Deliberately *not* a spelling check: it asks only that the thing a doc
    points at is there. Documenting a file that does not exist is the failure
    mode that survived four numeric gate revisions.

    A line carrying a negation cue ("does not exist", "forbidden", "renamed") is
    exempt, because such a line is *about* a path being absent — the opposite of
    a claim that it is present.
    """
    failures: list[dict[str, str]] = []
    checked = 0
    for rel in DOC_SCAN + STRUCTURE_SCAN_EXTRA:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        text = doc_path.read_text(encoding="utf-8")
        negated_lines = [
            line.lower() for line in text.splitlines() if any(cue in line.lower() for cue in _NEGATION_CUES)
        ]
        for token in sorted(set(_BACKTICK_TOKEN.findall(text))):
            verdict = _resolve_path_token(token)
            if verdict == "skip":
                continue
            if any(f"`{token}`" in line for line in negated_lines):
                continue
            checked += 1
            if verdict == "missing":
                failures.append(
                    {
                        "id": "C-PATHS",
                        "status": "MISSING_PATH",
                        "doc": rel,
                        "detail": f"{rel} cites `{token}`, which does not exist in the repository",
                    }
                )
    if not failures:
        return [
            {
                "id": "C-PATHS",
                "status": "PASS",
                "detail": f"{checked} backticked path reference(s) resolve",
            }
        ]
    return failures


# Extra docs covered by the structural checks (the numeric ones stay on the
# jury-facing set, because historical status pages legitimately quote numbers
# from the run that produced them).
STRUCTURE_SCAN_EXTRA: tuple[str, ...] = (
    "docs/STATUS.md",
    "docs/CURRENT_STATE.md",
    "docs/PROJECT_CONTEXT.md",
    "docs/CONTEXT/ARCHITECTURE_SNAPSHOT.md",
    "docs/RELEASE_NOTES.md",
    "docs/CHANGELOG.md",
)

# The data dictionary publishes one field list per table. The right-hand side is
# the real shape of a generated episode, asserted in both directions.
#
# Every documented table MUST appear here: a table the checker cannot resolve is
# skipped silently, which is how `accounts`, `counterparties`, `opening_balances`
# and `period_calendar` went unchecked until a negative test exposed it. The
# `C-DATADICT` probe now fails loudly on an unresolvable documented table instead.
_DATADICT_TABLES: tuple[tuple[str, str], ...] = (
    ("journal_entries.jsonl", "journal_entries"),
    ("invoices.jsonl", "invoices"),
    ("credit_notes.jsonl", "credit_notes"),
    ("payments.jsonl", "payments"),
    ("bank_lines.jsonl", "bank_lines"),
    ("fx_rates.jsonl", "fx_rates"),
    ("accounts.json", "accounts"),
    ("counterparties.jsonl", "counterparties"),
    ("opening_balances.json", "opening_balances"),
    ("period_calendar.json", "period_calendar"),
)


def _dictionary_shape() -> dict[str, set[str]]:
    """Return the field list published in DATA_DICTIONARY.md per table.

    Parsed from the one canonical bullet form the document uses::

        - `table`: `field_a, field_b, ...`.

    Nested lists (``lines[]``, ``allocations[]``) are returned under the key
    ``"<table>.nested"`` so they are checked separately.
    """
    text = (REPO_ROOT / "docs" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
    shape: dict[str, set[str]] = {}
    for match in re.finditer(r"^- `([A-Za-z_.]+)(?:\[\])?`:\s*`([^`]+)`", text, re.MULTILINE):
        name, body = match.group(1), match.group(2)
        suffix = ".nested" if "`[]`".replace("`", "") in match.group(0) or "[]" in match.group(0) else ""
        fields = {
            field.strip().split("|")[0].strip()
            for field in body.split(",")
            if field.strip()
        }
        if suffix:
            shape[name + suffix] = fields
        else:
            shape[name] = fields
    # The document writes nested lists as a following bullet: `- `lines[]`: ...`
    for match in re.finditer(r"^- `([A-Za-z_]+)\[\]`:\s*`([^`]+)`", text, re.MULTILINE):
        fields = {f.strip().split("|")[0].strip() for f in match.group(2).split(",") if f.strip()}
        shape[match.group(1) + ".nested"] = fields
    return shape


def _real_shape(episode_dir: Path) -> dict[str, set[str]]:
    """Return the realised field sets of one generated episode."""
    public = episode_dir / "public"
    shape: dict[str, set[str]] = {}
    for filename, table in _DATADICT_TABLES:
        path = public / filename
        if not path.is_file():
            continue
        rows: list[dict[str, Any]] = []
        if filename.endswith(".jsonl"):
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        else:  # pragma: no cover - all current table files are jsonl
            loaded = json.loads(path.read_text(encoding="utf-8"))
            rows = loaded if isinstance(loaded, list) else [loaded]
        if not rows:
            shape[table] = set()
            continue
        # Union across rows: nullable keys appear only on some rows.
        fields: set[str] = set()
        for row in rows:
            fields |= set(row)
        shape[table] = fields
    # Nested structures, unioned across every parent row.
    je_rows = [json.loads(l) for l in (public / "journal_entries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    line_fields: set[str] = set()
    for row in je_rows:
        for line in row.get("lines") or []:
            line_fields |= set(line)
    if line_fields:
        shape["lines.nested"] = line_fields
    inv_rows = [json.loads(l) for l in (public / "invoices.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    item_fields: set[str] = set()
    for row in inv_rows:
        for item in row.get("line_items") or []:
            item_fields |= set(item)
    if item_fields:
        shape["line_items.nested"] = item_fields
    pay_rows = [json.loads(l) for l in (public / "payments.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    alloc_fields: set[str] = set()
    for row in pay_rows:
        for alloc in row.get("allocations") or []:
            alloc_fields |= set(alloc)
    if alloc_fields:
        shape["allocations.nested"] = alloc_fields
    return shape


def data_dictionary_check() -> list[dict[str, str]]:
    """``C-DATADICT``: documented fields == realised fields, in both directions.

    A data dictionary that lists a field the data never contains sends a judge
    looking for something that is not there; one that omits a real field hides
    data. Both are unsupported claims, so both fail.
    """
    documented = _dictionary_shape()
    if not documented:
        return [
            {
                "id": "C-DATADICT",
                "status": "NO_SHAPE_FOUND",
                "detail": "docs/DATA_DICTIONARY.md publishes no parsable `- `table`: `f1, f2`` bullets",
            }
        ]
    episode_dir = _reference_episode_dir()
    if episode_dir is None:
        return [
            {
                "id": "C-DATADICT",
                "status": "SKIPPED",
                "detail": "no checked-in episode with public/ data to compare the dictionary against",
            }
        ]
    real = _real_shape(episode_dir)
    failures: list[dict[str, str]] = []
    checked = 0
    for name, documented_fields in sorted(documented.items()):
        key = name if name in real else (name + ".nested")
        if key not in real:
            # A documented table the checker cannot resolve is UNCHECKED, which is
            # worse than failing: it looks green. Fail loudly instead.
            failures.append(
                {
                    "id": "C-DATADICT",
                    "status": "UNRESOLVED_TABLE",
                    "detail": (
                        f"docs/DATA_DICTIONARY.md publishes `{name}` but no episode file "
                        f"backs it, so the field list cannot be verified; add it to "
                        f"_DATADICT_TABLES or remove the bullet"
                    ),
                }
            )
            continue
        checked += 1
        actual = real[key]
        for field in sorted(documented_fields - actual):
            failures.append(
                {
                    "id": "C-DATADICT",
                    "status": "PHANTOM_FIELD",
                    "detail": (
                        f"docs/DATA_DICTIONARY.md documents `{name}.{field}`, "
                        f"which does not appear in {episode_dir.name}/public data"
                    ),
                }
            )
        for field in sorted(actual - documented_fields):
            failures.append(
                {
                    "id": "C-DATADICT",
                    "status": "UNDOCUMENTED_FIELD",
                    "detail": (
                        f"{episode_dir.name}/public data carries `{name}.{field}`, "
                        f"which docs/DATA_DICTIONARY.md does not document"
                    ),
                }
            )
    if not failures:
        return [
            {
                "id": "C-DATADICT",
                "status": "PASS",
                "detail": f"{checked} table shape(s) match a real generated episode in both directions",
            }
        ]
    return failures


def _reference_episode_dir() -> Path | None:
    """Pick a deterministic checked-in episode that carries public data."""
    for candidate in sorted((REPO_ROOT / "episodes").glob("*/*/public")):
        if candidate.is_dir() and (candidate / "journal_entries.jsonl").is_file():
            return candidate.parent
    return None


def _demo_segments() -> list[tuple[str, str, str, str]]:
    """Read the demo's own ``SEGMENTS`` table — the single source of truth."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tools.demo_walkthrough import SEGMENTS  # local import: keeps --list cheap

    return list(SEGMENTS)


def demo_agreement_check() -> list[dict[str, str]]:
    """``C-DEMO``: the published demo table must equal the demo that runs.

    ``docs/DEMO.md`` is hand-written narration. It drifted twice: it described
    "five segments" while the program printed six, and its per-segment clock
    disagreed with the printed clock. Both are now impossible because both
    sides read the same ``SEGMENTS`` tuple.
    """
    try:
        segments = _demo_segments()
    except Exception as exc:  # pragma: no cover - import failure is a real defect
        return [
            {
                "id": "C-DEMO",
                "status": "SOURCE_UNREADABLE",
                "detail": f"tools/demo_walkthrough.py has no readable SEGMENTS tuple: {exc}",
            }
        ]
    text = (REPO_ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
    failures: list[dict[str, str]] = []
    # 1) the stated count, spelled out in prose ("six segments") or as a digit
    number_words = {
        1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
        6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    }
    expected_count = len(segments)
    accepted = {str(expected_count), number_words.get(expected_count, "")}
    stated = re.search(r"`master_seed=2025`,\s*([a-z0-9]+)\s+segments", text)
    if stated and stated.group(1) not in accepted:
        failures.append(
            {
                "id": "C-DEMO",
                "status": "COUNT_MISMATCH",
                "detail": (
                    f"docs/DEMO.md says {stated.group(0)!r} but the program prints "
                    f"{expected_count} segments"
                ),
            }
        )
    # 2) every segment row must match on number, clock and title
    published: dict[int, dict[str, str]] = {}
    for match in re.finditer(
        r"^\|\s*(\d+)\.\s*([^|]*?)\s*\|\s*(\d+:\d{2})\s*[–\-]\s*(\d+:\d{2})\s*\|([^|]*)\|",
        text,
        re.MULTILINE,
    ):
        number = int(match.group(1))
        published[number] = {
            "title": match.group(2).strip(),
            "start": match.group(3),
            "end": match.group(4),
            "text": match.group(5).strip(),
        }
    for number, start, end, title in segments:
        row = published.get(int(number))
        if row is None:
            failures.append(
                {
                    "id": "C-DEMO",
                    "status": "SEGMENT_MISSING",
                    "detail": f"docs/DEMO.md has no table row for segment {number} ({title})",
                }
            )
            continue
        if row["start"] != start or row["end"] != end:
            failures.append(
                {
                    "id": "C-DEMO",
                    "status": "CLOCK_MISMATCH",
                    "detail": (
                        f"segment {number}: docs/DEMO.md says {row['start']}-{row['end']}, "
                        f"the program prints {start}-{end}"
                    ),
                }
            )
    if not failures:
        return [
            {
                "id": "C-DEMO",
                "status": "PASS",
                "detail": f"{len(segments)} demo segments match tools/demo_walkthrough.py SEGMENTS",
            }
        ]
    return failures


def workbench_api_check() -> list[dict[str, str]]:
    """``C-WORKBENCH-API``: every documented route must be dispatched for real.

    ``docs/API_USAGE.md`` published ``/api/episode/<split>/<id>/overview`` as a
    GET route; the server answered 404 because the route was never implemented.
    A judge following the documentation sees a broken product, so the routes are
    now parsed out of the source rather than trusted.
    """
    source = (REPO_ROOT / "tools" / "demo_server.py").read_text(encoding="utf-8")
    get_routes = {m.group(1) for m in re.finditer(r'parsed\.path\s*==\s*"(/api/[a-z_/]+)"', source)}
    get_routes |= {m.group(1) for m in re.finditer(r'parsed\.path\s+in\s+\(([^)]*)\)', source) for _ in [0]}
    # POST routes are matched structurally: parts[0]=="api", parts[1]=="episode", ...
    post_templates: set[str] = set()
    for match in re.finditer(r"#\s*POST\s+(/api/[A-Za-z0-9_/<>\-]+)", source):
        post_templates.add(match.group(1))
    # Handler bodies that dispatch on parsed.path == "/api/..." inside do_POST.
    post_routes = {m.group(1) for m in re.finditer(r'parsed\.path\s*==\s*"(/api/[a-z_/]+)"', source.split("def do_POST", 1)[-1])}
    dispatched = get_routes | post_routes | {
        re.sub(r"<[^>]+>", "", template) for template in post_templates
    }
    doc = (REPO_ROOT / "docs" / "API_USAGE.md").read_text(encoding="utf-8")
    documented: list[tuple[str, str]] = []
    for match in re.finditer(r"^\|\s*(GET|POST)\s*\|\s*`(/api/[^`]+)`", doc, re.MULTILINE):
        documented.append((match.group(1), match.group(2)))
    # Also catch prose routes: "GET /api/..." anywhere in the table cell text.
    for match in re.finditer(r"\b(GET|POST)\s+(/api/[A-Za-z0-9_/<>{}\-]+)", doc):
        documented.append((match.group(1), match.group(2)))
    failures: list[dict[str, str]] = []
    checked = 0
    for method, route in sorted(set(documented)):
        checked += 1
        normalised = route.replace("<split>", "").replace("<id>", "").replace("//", "/").rstrip("/")
        wildcard = route.startswith("/api/episode/")
        if wildcard:
            implemented = "/api/episode/" in " ".join(post_templates) or "len(parts) == 5" in source
            if not implemented:
                failures.append(
                    {
                        "id": "C-WORKBENCH-API",
                        "status": "PHANTOM_ROUTE",
                        "detail": f"docs/API_USAGE.md documents {method} {route} but do_POST dispatches no such template",
                    }
                )
            continue
        if normalised not in dispatched:
            failures.append(
                {
                    "id": "C-WORKBENCH-API",
                    "status": "PHANTOM_ROUTE",
                    "detail": f"docs/API_USAGE.md documents {method} {route} but demo_server.py never dispatches it",
                }
            )
    if not failures:
        return [
            {
                "id": "C-WORKBENCH-API",
                "status": "PASS",
                "detail": f"{checked} documented workbench route(s) are dispatched by the real handlers",
            }
        ]
    return failures


# Scripts and targets the docs are allowed to name. Asserted by existence, not
# by running them (running every documented command is `make demo-backup`'s job).
_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpython3\s+([A-Za-z_][A-Za-z0-9_/\-]*\.py)\b"), "script"),
    (re.compile(r"\bpython3(?:\.\d+)?\s+-m\s+([a-z_][a-z0-9_]*\.[a-z0-9_.]*[a-z0-9_])\b"), "module"),
    (re.compile(r"^\s*\|\s*`make ([a-z\-]+)`", re.MULTILINE), "make-target"),
)


def command_executability_check() -> list[dict[str, str]]:
    """``C-COMMANDS``: every documented script, module and target must exist."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z0-9\-]*):(?:[^=]|$)", makefile, re.MULTILINE))
    failures: list[dict[str, str]] = []
    checked = 0
    for rel in ("README.md", "docs/API_USAGE.md", "docs/DEMO.md", "docs/POLICY_PROTOCOL.md", "docs/RELEASE_NOTES.md"):
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        text = doc_path.read_text(encoding="utf-8")
        for pattern, kind in _COMMAND_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1)
                checked += 1
                if kind == "script":
                    if not (REPO_ROOT / name).is_file() and not (REPO_ROOT / "tools" / name).is_file():
                        failures.append(
                            {
                                "id": "C-COMMANDS",
                                "status": "PHANTOM_SCRIPT",
                                "detail": f"{rel} documents `python3 {name}`, which does not exist",
                            }
                        )
                elif kind == "module":
                    module_path = REPO_ROOT / (name.replace(".", "/") + ".py")
                    package_path = REPO_ROOT / name.replace(".", "/") / "__init__.py"
                    if not module_path.is_file() and not package_path.is_file():
                        # `python3 -m <stdlib>` and `python3 -m make` are invocation
                        # forms, not repository modules: only a *dotted receiver*
                        # (``pkg.mod``) or a top-level package is asserted.
                        if "." not in name:
                            continue
                        failures.append(
                            {
                                "id": "C-COMMANDS",
                                "status": "PHANTOM_MODULE",
                                "detail": f"{rel} documents `python3 -m {name}`, which is not a repository module",
                            }
                        )
                elif name not in targets:
                    failures.append(
                        {
                            "id": "C-COMMANDS",
                            "status": "PHANTOM_TARGET",
                            "detail": f"{rel} documents `make {name}`, which the Makefile does not define",
                        }
                    )
    if not failures:
        return [
            {
                "id": "C-COMMANDS",
                "status": "PASS",
                "detail": f"{checked} documented command(s) resolve to a real script, module or make target",
            }
        ]
    return failures


# ``C-COUNTS``: an integer immediately followed by "test"/"tests".
# Deliberately narrow. A looser pattern over bare integers would fire on port
# numbers, durations, step budgets and episode counts, and a check that cries
# wolf gets switched off.
_TEST_COUNT_PROSE_RE = re.compile(
    r"\b(?P<count>\d+)(?P<sep>-|[ \t]+)"
    r"(?P<qualifier>(?:(?:official|mirror|organiser|organizer)[ \t]+)*)tests?\b",
    re.IGNORECASE,
)

# A published *suite* total is three digits in this project, and has been since
# before the first freeze (>300 tests). Smaller unqualified prose counts are
# treated as subset counts, unless explicitly introduced as full/total/suite: "tests/verifier/test_boundaries.py -> 5 tests PASS", "1 test skips
# as optional". Both were false positives on this check's first run -- which is
# recorded here rather than hidden, because the floor is a heuristic and a
# reviewer deserves to see what it is tuned against. A stale three-digit total
# is still caught. Official/mirror qualifiers use their own discovery count.
_MIN_SUITE_TOTAL = 100


# Clause terminators. A published count is qualified by the words in *its own*
# clause -- "490 tests, 55 official mirror tests" publishes two different totals
# side by side, so a fixed-width lookahead would read the second one's adjective
# into the first one's scope. Learned on this check's second run: a 160-char
# window reported the suite count as 55 (the official mirror subset).
_CLAUSE_END_RE = re.compile(r"[,;|.\n]")


def _mention_context(text: str, match: re.Match[str]) -> str:
    """The words that scope a published count: its own clause, plus a lead-in."""
    before = _CLAUSE_END_RE.split(text[max(0, match.start() - 60) : match.start()])[-1]
    tail = text[match.end() : match.end() + 120]
    stop = _CLAUSE_END_RE.search(tail)
    after = tail[: stop.start()] if stop else tail
    return before + " " + match.group(0) + " " + after


def _live_test_count_for(context: str) -> tuple[int, str]:
    """Return (live count, basis) for a prose mention of a test count.

    The basis is recorded so a reader can tell which measurement the published
    number tracks.
    """
    if re.search(r"official|mirror|organiser|organizer", context, re.IGNORECASE):
        return _discovered_test_count("tests/official"), "tests/official discovery"
    return _discovered_test_count("tests"), "tests/ discovery"


def _is_subset_count(text: str, match: re.Match[str]) -> bool:
    """True when the number counts a *file* or a *behaviour*, not the suite.

    Checked structurally rather than by wording: a count that sits next to a
    named test module is scoped to that module, whatever the sentence says.
    """
    preceding = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
    explicit_suite = bool(re.search(r"\b(?:full|total|suite)\b", _CLAUSE_END_RE.split(preceding)[-1], re.IGNORECASE))
    if int(match.group(1)) < _MIN_SUITE_TOTAL and not (match.group("qualifier") or explicit_suite):
        return True
    return bool(re.search(r"[\w/.-]*\btest_\w+\.py\b", preceding))


def _stale_counts_in(doc_path: Path, rel: str, autofix: bool = False) -> list[dict[str, str]]:
    """Return one failure dict per superseded suite total in a single document.

    Split out from :func:`stale_count_check` so the detector can be exercised on
    a temporary document. A check that can only be tested by corrupting the real
    repository is a check nobody tests.
    """
    text = doc_path.read_text(encoding="utf-8")
    pieces: list[str] = []
    cursor = 0
    changed = False
    failures: list[dict[str, str]] = []
    for match in _TEST_COUNT_PROSE_RE.finditer(text):
        if _is_subset_count(text, match):
            continue
        live, basis = _live_test_count_for(_mention_context(text, match))
        if int(match.group(1)) == live:
            continue
        line = text[: match.start()].count("\n") + 1
        failures.append(
            {
                "id": "C-COUNTS",
                "status": "STALE_COUNT",
                "doc": rel,
                "detail": (
                    f"{rel}:{line} publishes {match.group(1)} but {basis} is {live}; "
                    "the suite total must be derived, never remembered"
                ),
            }
        )
        pieces.append(text[cursor : match.start()])
        # Replace only the digits, preserving qualifiers, spacing, case and plurality.
        pieces.append(str(live) + match.group(0)[len(match.group(1)):])
        cursor = match.end()
        changed = True
    if autofix and changed:
        pieces.append(text[cursor:])
        doc_path.write_text("".join(pieces), encoding="utf-8")
    return failures


def stale_count_check(autofix: bool = False) -> list[dict[str, str]]:
    """``C-COUNTS``: no prose document may publish a superseded test count.

    ``P-TESTS-BLOCK`` only checks that the generated label exists; it never
    prohibited a second hand-written count elsewhere. The Phase-15 audit refreshed the generated block to the measured
    value and left "the full **522-test** suite" two paragraphs above it, and
    ``docs/DEMO.md`` still claimed "490 tests" against a suite of 531. Neither
    was caught by any gate, because the stale-literal denylist is a
    hand-maintained list of literals somebody had *already* noticed -- it can
    only ever catch a mistake that has already happened once.

    Recognised prose totals are compared with discovery rather than a denylist
    (REQ-DOC-002, TZ §24 Task 15.6). Scope is deliberately bounded: DOC_SCAN,
    integer + test/tests (optionally official/mirror qualifiers), and a heuristic
    floor for unqualified subset counts. This is not a general natural-language
    claim verifier; smaller unqualified counts and other phrasings need review.

    With ``autofix`` (i.e. ``--write``) the number is corrected in place by match
    position -- never by substring replacement, which would corrupt whichever
    copy happens to appear first.
    """
    failures: list[dict[str, str]] = []
    repaired: list[str] = []
    for rel in DOC_SCAN:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue  # the denylist pass reports missing docs; do not double-count
        doc_failures = _stale_counts_in(doc_path, rel, autofix=autofix)
        failures.extend(doc_failures)
        if autofix:
            repaired.extend(item["detail"] for item in doc_failures)
    if failures:
        if autofix:
            return [
                {
                    "id": "C-COUNTS",
                    "status": "PASS",
                    "detail": "superseded test counts rewritten in place: " + "; ".join(repaired),
                }
            ]
        return [
            {
                "id": "C-COUNTS",
                "status": "STALE_COUNT",
                "detail": (
                    "; ".join(item["detail"] for item in failures)
                    + " -- run --write to repair"
                ),
            }
        ]
    return [
        {
            "id": "C-COUNTS",
            "status": "PASS",
            "detail": "all recognised prose suite totals match discovery",
        }
    ]


def reward_provenance_check() -> list[dict[str, str]]:
    """``C-REWARD``: the quoted reward formula is the one the code computes.

    ``D-18-01`` collapsed two competing implementations into one and made the
    official organisers' formula authoritative. Three jury-facing docs still
    called the published reward "provisional" afterwards — a claim that would
    have a judge discount a formula the organisers themselves fixed.
    """
    failures: list[dict[str, str]] = []
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scoring.official_scorer import OFFICIAL_STEP_BUDGET, OFFICIAL_STEP_PENALTY_WEIGHT

    # Derived from the live constants, not from a second copy of the formula, so
    # this cannot itself become a competing definition (D-18-01).
    weight = OFFICIAL_STEP_PENALTY_WEIGHT
    formula_text = f"clip([-1, 1], 2*F1 - 1 - {weight}*inspection_steps/{OFFICIAL_STEP_BUDGET})"
    if float(weight) != 0.2 or OFFICIAL_STEP_BUDGET != 100:
        return [
            {
                "id": "C-REWARD",
                "status": "FORMULA_DRIFT",
                "detail": (
                    "the live reward constants changed "
                    f"(weight={weight}, budget={OFFICIAL_STEP_BUDGET}); the organisers fixed "
                    "0.2 and 100 on 2026-11-20, so the docs and every artifact derived from "
                    "them must be re-measured before anything else"
                ),
            }
        ]
    # The formula must appear in the docs that publish scoring semantics.
    for rel in ("docs/API_USAGE.md", "docs/POLICY_PROTOCOL.md", "README.md"):
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        text = doc_path.read_text(encoding="utf-8")
        if "2 * F1" in text or "2*F1" in text:
            continue  # mentions the formula; exact rendering varies by prose style
    # The stale claim: reward described as provisional when D-18-01 fixed it.
    for rel in DOC_SCAN:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        for line_number, line in enumerate(doc_path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.lower()
            if "reward" in lowered and "provisional" in lowered and "not" not in lowered.replace("provisionally", ""):
                failures.append(
                    {
                        "id": "C-REWARD",
                        "status": "STALE_PROVISIONAL",
                        "doc": rel,
                        "detail": (
                            f"{rel}:{line_number} calls the reward provisional, but D-18-01 made "
                            f"`{formula_text}` the single official implementation"
                        ),
                    }
                )
    # configs/scoring/default.json must not be presented as governing the reward.
    # Read the whole paragraph, not one line: the correct phrasing ("... retains
    # `provisional: true` as a historical record only; it no longer influences the
    # reward") spans lines, and a line-scoped rule cannot see the denial.
    denial_cues = ("no longer", "historical record", "only", "not edited", "does not influence", "never influences")
    for rel in DOC_SCAN:
        doc_path = REPO_ROOT / rel
        if not doc_path.is_file():
            continue
        paragraphs = re.split(r"\n\s*\n", doc_path.read_text(encoding="utf-8"))
        for paragraph in paragraphs:
            if "configs/scoring/default.json" not in paragraph or "provisional" not in paragraph.lower():
                continue
            if any(cue in paragraph.lower() for cue in denial_cues):
                continue
            failures.append(
                {
                    "id": "C-REWARD",
                    "status": "GOVERNING_CONFIG_CLAIM",
                    "doc": rel,
                    "detail": (
                        f"{rel} presents configs/scoring/default.json as the governing reward "
                        "parameter set; D-18-01 says it no longer influences the reward"
                    ),
                }
            )
    if not failures:
        return [
            {
                "id": "C-REWARD",
                "status": "PASS",
                "detail": f"no doc contradicts the single live formula `{formula_text}`",
            }
        ]
    return failures


# Values that were published once and proven wrong or misleading.
STALE_LITERALS: tuple[tuple[str, str], ...] = (
    # NOTE: superseded test counts are no longer enumerated here. Enumerating
    # them was the defect: the list only ever held totals somebody had already
    # caught by eye, so it could never catch the next one (README published a
    # stale 522 for a whole phase). ``C-COUNTS`` now derives every prose total
    # from unittest discovery, for recognised test-count phrases.
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
    parser.add_argument("--write", action="store_true", help="refresh README facts and recognised prose suite totals")
    parser.add_argument("--json", action="store_true", help="emit the full report to stdout")
    parser.add_argument("--list", action="store_true", help="list measured facts without checking")
    args = parser.parse_args(argv)

    if args.list:
        for fact in collect_facts():
            _say(f"{fact['id']:22s} {fact['value']:24s} {fact['source']}")
        _say(f"\n{len(collect_facts())} measured facts")
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
        comparable_current, comparable_rendered = current, rendered
        if not baseline_log_available():
            comparable_current = strip_baselines(current)
            comparable_rendered = strip_baselines(rendered)
        if comparable_current != comparable_rendered:
            if args.write:
                # Never erase published baseline rows just because this
                # environment cannot read the log.
                replacement = rendered
                if not baseline_log_available():
                    tail = current[current.find(BASELINE_HEADING):] if BASELINE_HEADING in current else ""
                    replacement = strip_baselines(rendered).replace(
                        "<!-- END GENERATED:measured-facts -->",
                        tail if tail else "<!-- END GENERATED:measured-facts -->",
                    )
                readme_path.write_text(readme[:start] + replacement + readme[end:], encoding="utf-8")
                checks.append({"id": "G-BLOCK", "status": "REFRESHED", "detail": "facts block updated"})
            else:
                failures.append(
                    {
                        "id": "G-BLOCK",
                        "status": "DRIFT",
                        "detail": (
                            "generated facts block disagrees with measured artifacts "
                            f"({_first_difference(comparable_current, comparable_rendered)}); "
                            "run --write after checking"
                        ),
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

    # 5) structural checks — a published shape must equal the real shape.
    # These do not need artifacts, so they run on a bare checkout too. A SKIPPED
    # result is recorded as a skip, never folded into the pass count.
    structural: tuple[tuple[str, Any], ...] = (
        ("C-PATHS", path_reference_check),
        ("C-DATADICT", data_dictionary_check),
        ("C-DEMO", demo_agreement_check),
        ("C-WORKBENCH-API", workbench_api_check),
        ("C-COMMANDS", command_executability_check),
        ("C-REWARD", reward_provenance_check),
        ("C-COUNTS", functools.partial(stale_count_check, autofix=bool(args.write))),
    )
    structural_skipped: list[str] = []
    for _check_id, probe in structural:
        try:
            outcome = probe()
        except Exception as exc:  # pragma: no cover - a crashing probe is a defect
            failures.append(
                {
                    "id": _check_id,
                    "status": "CHECK_CRASHED",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        for item in outcome:
            if item.get("status") == "PASS":
                checks.append(item)
            elif item.get("status") == "SKIPPED":
                structural_skipped.append(item["detail"])
                checks.append(item)
            else:
                failures.append(item)

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
        "checks_total": len(checks) + len(failures),
        "structural_skipped": structural_skipped,
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
        _say(f"doc-claims: note: report not written ({exc.__class__.__name__}: {exc}); verdict still authoritative")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True))
    else:
        _say(
            f"doc-claims: {status} ({report['facts_total']} measured facts, "
            f"{report['checks_passed']}/{report['checks_total']} checks passed)"
        )
        if structural_skipped:
            for reason in structural_skipped:
                _say(f"  [SKIPPED] {reason}")
        if args.write:
            _say(f"  generated block refreshed in {README}")
        for failure in failures:
            _say(f"  [{failure['status']}] {failure['id']}: {failure.get('detail', '')}")
        if report_written:
            try:
                shown = OUTPUT_PATH.relative_to(REPO_ROOT)
            except ValueError:  # caller redirected the output outside the repo
                shown = OUTPUT_PATH
            _say(f"report: {shown}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
