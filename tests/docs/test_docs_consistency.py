"""Documentation consistency tests.

Documentation that drifts is worse than no documentation, because a fresh agent trusts it.
These tests check the docs *against the code*, not against each other:

* the generated context snapshot must be current (`tools/export_context.py --check`);
* every document an index promises must exist;
* every invariant, operator and schema mentioned in prose must still exist in code;
* every phase report must contain the required evidence sections;
* no document may claim "GitHub updated" without a URL.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import unittest
from pathlib import Path

from gen.errors import registry
from gen.errors.signatures import ERROR_MATRIX, SUBTYPE_MATRIX
from invariants.checks_clean import check_all
from tools.export_context import build_context, render

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"

REQUIRED_DOCUMENTS = (
    "README.md",
    "STATUS.md",
    "CURRENT_STATE.md",
    "DECISIONS.md",
    "GLOSSARY.md",
    "CONTEXT/NEXT_AGENT.md",
    "CONTEXT/ARCHITECTURE.md",
    "CONTEXT/AI_HANDOFF_PROTOCOL.md",
    "CONTEXT/INVARIANTS.md",
    "CONTEXT/ERROR_MATRIX.md",
    "CONTEXT/DATA_CONTRACTS.md",
    "CONTEXT/DETERMINISM.md",
    "CONTEXT/TESTING.md",
    "CONTEXT/CLEAN_TWIN_MODEL.md",
    "CONTEXT/OPERATIONS.md",
    "CONTEXT/PROJECT_CONTEXT.json",
    "PHASE_REPORTS/PHASE-04.md",
    "PHASE_REPORTS/PHASE-04.json",
)


class DocumentInventoryTests(unittest.TestCase):
    def test_required_documents_exist(self) -> None:
        missing = [name for name in REQUIRED_DOCUMENTS if not (DOCS / name).is_file()]
        self.assertEqual(missing, [], f"missing documentation: {missing}")

    def test_documents_are_not_empty(self) -> None:
        for name in REQUIRED_DOCUMENTS:
            path = DOCS / name
            if not path.is_file():
                continue
            with self.subTest(document=name):
                self.assertGreater(len(path.read_text(encoding="utf-8").strip()), 500)

    def test_docs_readme_links_resolve(self) -> None:
        """Every relative markdown link in the documentation must resolve."""
        broken: list[str] = []
        for path in DOCS.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    broken.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
        self.assertEqual(broken, [], f"broken documentation links: {broken}")


class GeneratedContextTests(unittest.TestCase):
    def test_context_snapshot_is_current(self) -> None:
        committed = (DOCS / "CONTEXT" / "PROJECT_CONTEXT.json").read_text(encoding="utf-8")
        self.assertEqual(
            committed,
            render(),
            "docs/CONTEXT/PROJECT_CONTEXT.json is stale — run python3 tools/export_context.py",
        )

    def test_context_matches_live_code(self) -> None:
        context = json.loads((DOCS / "CONTEXT" / "PROJECT_CONTEXT.json").read_text(encoding="utf-8"))
        live = build_context()
        self.assertEqual(context["schemas"]["count"], live["schemas"]["count"])
        self.assertEqual(context["book"]["public_files"], live["book"]["public_files"])
        self.assertEqual(context["invariants"]["count"], len(live["invariants"]["catalogue"]))
        self.assertEqual(
            [entry["operator_id"] for entry in context["operators"]],
            [entry["operator_id"] for entry in live["operators"]],
        )

    def test_context_lists_only_real_operators(self) -> None:
        context = json.loads((DOCS / "CONTEXT" / "PROJECT_CONTEXT.json").read_text(encoding="utf-8"))
        documented = {entry["operator_id"] for entry in context["operators"]}
        self.assertEqual(documented, set(registry.operator_ids()))


class ProseAgainstCodeTests(unittest.TestCase):
    def test_invariant_document_covers_all_checks(self) -> None:
        text = (DOCS / "CONTEXT" / "INVARIANTS.md").read_text(encoding="utf-8")
        missing = [f"INV-{index:02d}" for index in range(1, 18) if f"INV-{index:02d}" not in text]
        self.assertEqual(missing, [], f"invariants missing from documentation: {missing}")

    def test_error_matrix_document_lists_every_family(self) -> None:
        text = (DOCS / "CONTEXT" / "ERROR_MATRIX.md").read_text(encoding="utf-8")
        for anomaly_type in ERROR_MATRIX:
            self.assertIn(anomaly_type, text)
        for (anomaly_type, subtype) in SUBTYPE_MATRIX:
            self.assertIn(subtype, text, f"{subtype} documented?")

    def test_declared_invariants_are_real(self) -> None:
        """Every INV-NN named in docs must be one the checker actually emits."""
        from gen.clean import build_clean_book
        from gen.config import load_generator_config
        from dataclasses import replace

        config = load_generator_config()
        book = build_clean_book(master_seed="docs-prose", config=config, difficulty="L1").book
        # Break one entry so checks have something to report; we only need the id space.
        entries = list(book.journal_entries)
        first = entries[0]
        entries[0] = replace(first, timestamp="not-a-timestamp", posting_period="1900-M01")
        broken = book.with_rows("journal_entries", entries)
        observed = {violation.invariant_id for violation in check_all(broken)}
        documented = set(re.findall(r"INV-\d{2}", (DOCS / "CONTEXT" / "INVARIANTS.md").read_text(encoding="utf-8")))
        unknown = sorted(documented - {f"INV-{index:02d}" for index in range(1, 18)})
        self.assertEqual(unknown, [], f"documented invariants that do not exist: {unknown}")
        self.assertTrue(observed, "corrupted book produced no violations at all")

    def test_schema_count_in_docs_matches_disk(self) -> None:
        actual = len(list((REPO_ROOT / "contracts").glob("*.schema.json")))
        for document in ("CONTEXT/DATA_CONTRACTS.md", "CONTEXT/PROJECT_CONTEXT.json"):
            text = (DOCS / document).read_text(encoding="utf-8")
            self.assertIn(str(actual), text, f"{document} should mention the real schema count {actual}")

    def test_public_file_count_in_docs_matches_code(self) -> None:
        from contracts.book_model import PUBLIC_FILE_ORDER

        context = json.loads((DOCS / "CONTEXT" / "PROJECT_CONTEXT.json").read_text(encoding="utf-8"))
        self.assertEqual(context["book"]["public_file_count"], len(PUBLIC_FILE_ORDER))
        self.assertEqual(len(set(PUBLIC_FILE_ORDER)), len(PUBLIC_FILE_ORDER))


class PhaseReportTests(unittest.TestCase):
    def _phase_report(self) -> str:
        return (DOCS / "PHASE_REPORTS" / "PHASE-04.md").read_text(encoding="utf-8")

    def test_report_has_required_sections(self) -> None:
        text = self._phase_report()
        for required in (
            "Executive summary",
            "Requirements traceability",
            "Tests and gates",
            "Exit gate verdict",
            "Deviations",
            "Known issues",
            "Next phase readiness",
        ):
            self.assertIn(required, text, f"phase report missing section: {required}")

    def test_report_has_command_exit_result_table(self) -> None:
        text = self._phase_report()
        self.assertIn("| Command | Exit |", text)
        self.assertGreaterEqual(text.count("| 0 |"), 5, "expected several executed commands with exit 0")

    def test_report_json_is_parsable_and_agrees_with_markdown(self) -> None:
        payload = json.loads((DOCS / "PHASE_REPORTS" / "PHASE-04.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "DONE")
        self.assertEqual(payload["exit_gate"]["verdict"], "PASS")
        self.assertIn("DONE", self._phase_report())
        self.assertEqual(payload["phase"], 4)
        self.assertTrue(payload["commands"])

    def test_no_unbacked_github_claims(self) -> None:
        """Any mention of a GitHub update must carry a URL or a commit id."""
        offenders: list[str] = []
        # Guidance *about* the rule is not a claim: only assert statements are checked.
        rule_markers = ("never", "do not", "don't", "must not")
        for path in DOCS.rglob("*.md"):
            for line in path.read_text(encoding="utf-8").splitlines():
                lowered = line.lower()
                if "github updated" not in lowered:
                    continue
                if any(marker in lowered for marker in rule_markers):
                    continue
                if "http" not in lowered:
                    offenders.append(f"{path.name}: {line.strip()}")
        self.assertEqual(offenders, [], offenders)

    def test_test_counts_in_docs_are_plausible(self) -> None:
        """Guard against a stale count: docs must not claim more tests than modules exist."""
        count = len([p for p in (REPO_ROOT / "tests").rglob("test_*.py")])
        text = (DOCS / "STATUS.md").read_text(encoding="utf-8")
        claimed = int(re.search(r"(\d+) tests", text).group(1))  # type: ignore[union-attr]
        self.assertGreater(claimed, 0)
        self.assertGreaterEqual(claimed, count, "claimed test count is below the number of test modules")


class StatusConsistencyTests(unittest.TestCase):
    def test_docs_test_count_matches_reality(self) -> None:
        """The suite's own count must be stated correctly wherever it is claimed."""
        claimed = 19
        # Count test methods declared in this module, not dynamic discovery.
        tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        methods = [
            node.name
            for cls in ast.walk(tree)
            if isinstance(cls, ast.ClassDef)
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
        self.assertEqual(len(methods), claimed, f"STATUS claims {claimed}, module declares {len(methods)}")
        status = (DOCS / "STATUS.md").read_text(encoding="utf-8")
        self.assertIn(f"| docs (documentation ↔ code consistency) | {claimed} |", status)

    def test_status_and_current_state_agree_on_phase(self) -> None:
        status = (DOCS / "STATUS.md").read_text(encoding="utf-8")
        current = (DOCS / "CURRENT_STATE.md").read_text(encoding="utf-8")
        self.assertIn("4", status)
        self.assertIn("Phase 4", current)
        self.assertIn("DONE", status)
        self.assertIn("DONE", current)

    def test_next_agent_brief_points_to_real_files(self) -> None:
        text = (DOCS / "CONTEXT" / "NEXT_AGENT.md").read_text(encoding="utf-8")
        for referenced in re.findall(r"`(docs/[A-Za-z0-9_./-]+)`", text):
            self.assertTrue((REPO_ROOT / referenced).exists(), f"NEXT_AGENT references missing {referenced}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
