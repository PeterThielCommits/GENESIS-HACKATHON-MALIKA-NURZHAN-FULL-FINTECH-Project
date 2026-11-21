"""Import and file-access boundary tests for the independent verifier
(Phase 8, Task 8.7 — REQ-ARC-001, REQ-ARC-007, REQ-ORG-004, REQ-VER-001..002).

Proves BOTH statically (AST scan) and dynamically (runtime sys.modules +
filesystem access spy) that verifier discovery:
  - never imports ``gen``, ``core``, ``invariants``, ``scoring``, ``env``,
    ``harness``, ``seal``, or ``arena``;
  - never references private/non-public path literals;
  - ONLY reads allowlisted files inside ``public/`` and NEVER touches sibling
    sealed directories or hidden files even when present next to ``public/``;
  - rejects hidden files, ``index_hints.json``, non-allowlisted files, and
    symlinks escaping ``public/``.
"""

from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.verifier import fixtures as fx
from tools.check_import_boundaries import scan as repo_boundary_scan
from verifier import PublicEpisodeError, discover, load_public_episode

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFIER_DIR = REPO_ROOT / "verifier"

FORBIDDEN_VERIFIER_TOP_IMPORTS = frozenset(
    {"gen", "core", "invariants", "scoring", "env", "harness", "seal", "arena"}
)


class TestVerifierBoundaries(unittest.TestCase):
    def test_repo_import_boundary_scanner_is_clean(self):
        self.assertEqual(repo_boundary_scan(REPO_ROOT), [])

    def test_verifier_ast_strictly_independent_of_gen_and_shared_detectors(self):
        py_files = sorted(VERIFIER_DIR.rglob("*.py"))
        self.assertGreaterEqual(len(py_files), 10)
        for path in py_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        self.assertNotIn(
                            top,
                            FORBIDDEN_VERIFIER_TOP_IMPORTS,
                            msg=f"{path.name}:{node.lineno} imports forbidden {alias.name!r}",
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    top = node.module.split(".")[0]
                    self.assertNotIn(
                        top,
                        FORBIDDEN_VERIFIER_TOP_IMPORTS,
                        msg=f"{path.name}:{node.lineno} imports from forbidden {node.module!r}",
                    )

    def test_fresh_process_importing_verifier_never_loads_gen_or_scoring(self):
        code = (
            "import sys, verifier; "
            "bad = [m for m in sys.modules if m.split('.')[0] in "
            "{'gen','core','invariants','scoring','env','harness','seal','arena'}]; "
            "assert not bad, f'unexpected loaded modules: {bad}'"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr + proc.stdout)

    def test_runtime_file_access_spy_never_leaves_public_dir(self):
        ep, _ = fx.compound_four_type_episode()
        with tempfile.TemporaryDirectory() as td:
            ep_root = Path(td)
            pub_dir = ep_root / "public"
            priv_dir = ep_root / "sealed"
            fx.write_public_dir(pub_dir, ep)
            priv_dir.mkdir()
            (priv_dir / "truth.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")
            (priv_dir / "provenance.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")
            (ep_root / "manifest.json").write_text('{"canary": "DO_NOT_READ"}\n', encoding="utf-8")

            pub_resolved = pub_dir.resolve()
            opened_paths: list[Path] = []
            real_io_open = io.open
            real_path_open = Path.open

            def spy_io_open(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)):
                    p = Path(file).resolve()
                    if ep_root.resolve() in p.parents or p == ep_root.resolve():
                        opened_paths.append(p)
                return real_io_open(file, *args, **kwargs)

            def spy_path_open(self_path, *args, **kwargs):
                p = self_path.resolve()
                if ep_root.resolve() in p.parents or p == ep_root.resolve():
                    opened_paths.append(p)
                return real_path_open(self_path, *args, **kwargs)

            with (
                mock.patch("io.open", side_effect=spy_io_open),
                mock.patch.object(Path, "open", spy_path_open),
            ):
                out = discover(pub_dir)

            self.assertEqual(len(out.report.findings), 4)
            self.assertGreater(len(opened_paths), 0)
            for p in opened_paths:
                self.assertTrue(
                    p.is_relative_to(pub_resolved),
                    msg=f"verifier accessed path outside public/: {p}",
                )
                self.assertNotIn("sealed", p.parts)

    def test_rejects_hidden_files_index_hints_extra_files_and_symlink_escape(self):
        ep = fx.clean_episode()

        # 1. Hidden dotfile inside public/
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "public"
            fx.write_public_dir(pub, ep)
            (pub / ".hidden_truth").write_text("x", encoding="utf-8")
            with self.assertRaises(PublicEpisodeError):
                load_public_episode(pub)

        # 2. Forbidden index_hints.json (TZ 8.2)
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "public"
            fx.write_public_dir(pub, ep)
            (pub / "index_hints.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(PublicEpisodeError):
                load_public_episode(pub)

        # 3. Unrecognised private file dropped into public/
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "public"
            fx.write_public_dir(pub, ep)
            (pub / "provenance.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(PublicEpisodeError):
                load_public_episode(pub)

        # 4. Symlink escaping public/ boundary
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pub = root / "public"
            outside = root / "outside_secret.json"
            outside.write_text(json.dumps(ep.company), encoding="utf-8")
            fx.write_public_dir(pub, ep)
            (pub / "company.json").unlink()
            (pub / "company.json").symlink_to(outside)
            with self.assertRaises(PublicEpisodeError):
                load_public_episode(pub)


if __name__ == "__main__":
    unittest.main()
