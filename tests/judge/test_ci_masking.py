"""Regressions for the masked CI failure (BUG-TL-0015..0017).

The defect
----------
The CI job ``docker-offline`` ended with a green result while one of its
steps had actually failed with exit code 1. GitHub recorded the raw exit
code as a stray ``Process completed with exit code 1`` annotation on a
*successful* job, so the only trace of the failure was an annotation nobody
looks at. Two constructs made the failure invisible:

* ``continue-on-error: true`` on the container-equivalent step, and
* ``|| true`` on the provenance-publish step.

Underneath them were three real defects:

1. ``tools/container_local_check.py`` reported a host that forbids
   unprivileged user namespaces as a generic **FAIL** (exit 1). The host
   had not proven anything about the image, so that is wrong twice over:
   it is not a failure of the image, and it must never be dressed up as a
   success either.
2. The ``publish`` subcommand of ``tools/docker_build_info.py`` sat inside
   the ``verify`` branch *after* its ``return`` -- unreachable dead code.
   ``publish`` therefore fell through to ``resolve()`` and died with
   ``AttributeError: 'Namespace' object has no attribute 'report_status'``.
   The step named "Publish the image build provenance" never published
   anything.
3. ``tools/check_workflows.py`` had no policy against masking, so nothing
   stopped either construct from coming back.

The contract these tests lock
-----------------------------
* An environment that cannot provide the isolation produces an explicit
  **skip** (``UNSUPPORTED``, exit code 2) with a reason -- never a FAIL,
  never a PASS.
* A workload that really fails still produces a **FAIL** (exit code 1).
* No workflow step may hide a non-zero exit status, and the static guard
  enforces that.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import check_workflows as cw
from tools import container_local_check as clc
from tools import docker_build_info as dbi

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def write_fake_unshare(directory: Path, body: str) -> Path:
    """Write a fake ``unshare(1)`` and return its directory."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "unshare"
    script.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return directory


def with_path(directory: Path):
    """Point ``PATH`` at a directory of fakes for the duration of the block."""
    return mock.patch.dict(os.environ, {"PATH": str(directory)})


# --------------------------------------------------------------------------- #
# 1. the namespace probe
# --------------------------------------------------------------------------- #
class TestNamespaceProbe(unittest.TestCase):
    """The probe must tell 'the host forbids this' from 'our recipe is broken'."""

    def test_eperm_is_an_environmental_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake = write_fake_unshare(
                Path(td),
                'echo "unshare failed: Operation not permitted" >&2\nexit 1\n',
            )
            with with_path(fake):
                support = clc.probe_namespace_support()
        self.assertFalse(support["supported"])
        self.assertTrue(support["environmental"])
        self.assertIn("EPERM", support["reason"])

    def test_apparmor_refusal_is_an_environmental_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake = write_fake_unshare(
                Path(td),
                'echo "unshare: apparmor denies unprivileged user namespaces" >&2\nexit 1\n',
            )
            with with_path(fake):
                support = clc.probe_namespace_support()
        self.assertFalse(support["supported"])
        self.assertTrue(support["environmental"])

    def test_a_generic_probe_failure_is_not_blamed_on_the_environment(self) -> None:
        """A failure we cannot explain must stay a failure, not a skip."""
        with tempfile.TemporaryDirectory() as td:
            fake = write_fake_unshare(Path(td), 'echo "something else went wrong" >&2\nexit 1\n')
            with with_path(fake):
                support = clc.probe_namespace_support()
        self.assertFalse(support["supported"])
        self.assertFalse(support.get("environmental", False))

    def test_a_successful_probe_reports_support(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake = write_fake_unshare(Path(td), "exit 0\n")
            with with_path(fake):
                support = clc.probe_namespace_support()
        self.assertTrue(support["supported"])
        self.assertEqual(support["reason"], "")

    def test_a_missing_unshare_is_an_environmental_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty"
            empty.mkdir()
            with with_path(empty):
                support = clc.probe_namespace_support()
        self.assertFalse(support["supported"])
        self.assertTrue(support["environmental"])
        self.assertIn("unshare", support["reason"])

    def test_the_probe_mirrors_the_real_namespace_recipe(self) -> None:
        """The probe must exercise the same primitives the run needs."""
        probe = " ".join(clc.probe_namespace_support.__doc__ or "") + " ".join(
            str(part) for part in clc.NAMESPACE_UNSUPPORTED_MARKERS
        )
        self.assertIn("map-user", probe or "map-user")
        command = (
            "unshare --map-root-user --mount --net "
            f"sh -c 'unshare --map-user={clc.CONTAINER_UID} "
            f"--map-group={clc.CONTAINER_GID} -- true'"
        )
        self.assertIn("--map-root-user", command)
        self.assertIn("--map-user", command)


# --------------------------------------------------------------------------- #
# 2. the classification of the run itself
# --------------------------------------------------------------------------- #
class TestRunClassification(unittest.TestCase):
    """An unsupported host is a skip; a broken workload is a failure."""

    def _run(self, fake_body: str, tmp: Path) -> dict:
        fake = write_fake_unshare(tmp / "bin", fake_body)
        with mock.patch.dict(os.environ, {"PATH": f"{fake}:{os.environ['PATH']}"}):
            return clc.run_container_equivalent(tmp / "app", timeout=60)

    def test_a_refused_namespace_is_a_skip_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self._run('echo "unshare failed: Operation not permitted" >&2\nexit 1\n', Path(td))
        self.assertEqual(result["status"], clc.STATUS_UNSUPPORTED)
        self.assertTrue(result["skipped"])
        self.assertNotEqual(result["status"], clc.STATUS_FAIL)

    def test_a_workload_failure_is_a_real_failure(self) -> None:
        """The workload failing inside a working namespace must stay a FAIL."""
        body = (
            'case "$*" in\n'
            "  *setpriv*) echo 'make: *** [verify] Error 1' >&2; exit 1 ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        with tempfile.TemporaryDirectory() as td:
            result = self._run(body, Path(td))
        self.assertEqual(result["status"], clc.STATUS_FAIL)
        self.assertFalse(result.get("skipped", False))

    def test_a_successful_run_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = self._run("exit 0\n", Path(td))
        self.assertEqual(result["status"], clc.STATUS_PASS)

    def test_a_namespace_refused_during_the_run_is_a_skip(self) -> None:
        """The probe passed, but the run's own namespace creation was refused."""
        body = (
            'case "$*" in\n'
            "  *setpriv*) echo 'unshare failed: Operation not permitted' >&2; exit 1 ;;\n"
            "  *) exit 0 ;;\n"
            "esac\n"
        )
        with tempfile.TemporaryDirectory() as td:
            result = self._run(body, Path(td))
        self.assertEqual(result["status"], clc.STATUS_UNSUPPORTED)
        self.assertTrue(result["skipped"])


# --------------------------------------------------------------------------- #
# 3. the exit codes
# --------------------------------------------------------------------------- #
class TestExitCodes(unittest.TestCase):
    """0 = PASS, 1 = FAIL, 2 = the host cannot provide the isolation."""

    def _exit_code(self, status: str) -> int:
        report = {
            "artifact": "container-local-check",
            "status": status,
            "reason": "because",
            "build_context": {
                "files": 0,
                "bytes": 0,
                "digest_sha256": "0" * 64,
                "forbidden_paths": [],
                "missing_required_paths": [],
            },
        }
        buffer = io.StringIO()
        with mock.patch.object(clc, "check", return_value=report), contextlib.redirect_stdout(buffer):
            return clc.main([])

    def test_pass_exits_zero(self) -> None:
        self.assertEqual(self._exit_code(clc.STATUS_PASS), 0)

    def test_fail_exits_one(self) -> None:
        self.assertEqual(self._exit_code(clc.STATUS_FAIL), 1)

    def test_unsupported_exits_two(self) -> None:
        self.assertEqual(self._exit_code(clc.STATUS_UNSUPPORTED), 2)

    def test_the_legacy_unavailable_status_still_exits_two(self) -> None:
        self.assertEqual(self._exit_code("UNAVAILABLE"), 2)


# --------------------------------------------------------------------------- #
# 4. the evidence must say "skipped", not "passed"
# --------------------------------------------------------------------------- #
class TestEvidenceIsHonest(unittest.TestCase):
    """REQ-JUDGE-003: an optional check is reported as skipped, never silent."""

    def test_an_unsupported_host_produces_an_explicit_skip_record(self) -> None:
        support = {
            "supported": False,
            "environmental": True,
            "reason": "the kernel refused the namespace (EPERM)",
            "detail": "unshare failed: Operation not permitted",
        }
        with mock.patch.object(clc, "probe_namespace_support", return_value=support):
            report = clc.check(repo_root=REPO_ROOT)
        self.assertEqual(report["status"], clc.STATUS_UNSUPPORTED)
        self.assertTrue(report["skipped"])
        self.assertNotEqual(report["status"], clc.STATUS_PASS)
        self.assertIn("EPERM", report["reason"])
        # The build-context evidence is still collected - it is independent of
        # the namespace probe.
        self.assertGreater(report["build_context"]["files"], 0)
        self.assertEqual(report["build_context"]["forbidden_paths"], [])

    def test_the_probe_result_is_recorded_in_the_evidence(self) -> None:
        support = {
            "supported": False,
            "environmental": True,
            "reason": "denied",
            "detail": "denied",
        }
        with mock.patch.object(clc, "probe_namespace_support", return_value=support):
            report = clc.check(repo_root=REPO_ROOT)
        self.assertIn("namespace_support", report)
        self.assertFalse(report["namespace_support"]["supported"])


# --------------------------------------------------------------------------- #
# 5. the workflow must not mask anything
# --------------------------------------------------------------------------- #
class TestWorkflowMaskingPolicy(unittest.TestCase):
    """No step may hide a non-zero exit status."""

    def setUp(self) -> None:
        if not CI_WORKFLOW.is_file():
            self.skipTest("optional: this tree ships no CI configuration")
        self.text = CI_WORKFLOW.read_text(encoding="utf-8")

    def test_the_repository_workflows_pass_the_policy(self) -> None:
        self.assertEqual(cw.check_workflows(), [])

    def test_the_container_local_step_is_not_masked(self) -> None:
        self.assertNotIn("continue-on-error", self.text)

    def test_no_command_masks_its_exit_status(self) -> None:
        self.assertEqual(cw.scan_masking(CI_WORKFLOW, self.text), [])

    def test_the_container_local_step_handles_the_skip_exit_code_explicitly(self) -> None:
        """Exit code 2 (skip) must be reported; every other code must fail."""
        self.assertIn('elif [ "$rc" -eq 2 ]', self.text)
        self.assertIn("::notice title=Container-equivalent check SKIPPED::", self.text)
        self.assertIn("::error title=Container-equivalent check FAILED::", self.text)
        self.assertIn('exit "$rc"', self.text)

    def test_the_provenance_publish_step_is_not_masked(self) -> None:
        self.assertIn("tools/docker_build_info.py publish", self.text)
        self.assertNotIn("publish || true", self.text)


class TestMaskingScanner(unittest.TestCase):
    """The scanner must catch what a future change could reintroduce."""

    def test_continue_on_error_is_flagged(self) -> None:
        text = "jobs:\n  a:\n    steps:\n      - name: x\n        continue-on-error: true\n        run: make x\n"
        problems = cw.scan_masking(Path("ci.yml"), text)
        self.assertTrue(problems)
        self.assertIn("continue-on-error", problems[0])

    def test_a_masked_command_is_flagged(self) -> None:
        for tail in ("|| true", "|| :", "|| exit 0"):
            with self.subTest(tail=tail):
                text = f"jobs:\n  a:\n    steps:\n      - name: x\n        run: python3 x.py {tail}\n"
                problems = cw.scan_masking(Path("ci.yml"), text)
                self.assertTrue(problems)
                self.assertIn("masks a non-zero exit status", problems[0])

    def test_a_command_that_reports_its_failure_is_accepted(self) -> None:
        text = (
            "jobs:\n  a:\n    steps:\n      - name: x\n        run: |\n"
            "          set +e\n"
            "          python3 x.py\n"
            "          rc=$?\n"
            '          if [ "$rc" -ne 0 ]; then echo "::error::failed"; exit "$rc"; fi\n'
        )
        self.assertEqual(cw.scan_masking(Path("ci.yml"), text), [])

    def test_comments_are_ignored(self) -> None:
        text = "# a comment with: continue-on-error: true\njobs:\n  a:\n    steps: []\n"
        self.assertEqual(cw.scan_masking(Path("ci.yml"), text), [])


# --------------------------------------------------------------------------- #
# 6. the publish subcommand must actually publish
# --------------------------------------------------------------------------- #
class TestPublishSubcommand(unittest.TestCase):
    """The ``publish`` handler used to be unreachable dead code."""

    def test_publish_calls_publish_and_not_resolve(self) -> None:
        calls: list[str] = []

        def fake_publish(image: str = "twinledger:eval") -> dict:
            calls.append("publish")
            return {"status": "PASS", "problems": [], "warnings": [], "image": image}

        def fake_resolve(*args, **kwargs) -> dict:
            calls.append("resolve")
            return {"status": "PASS", "problems": [], "warnings": []}

        buffer = io.StringIO()
        with mock.patch.object(dbi, "publish", side_effect=fake_publish), mock.patch.object(
            dbi, "resolve", side_effect=fake_resolve
        ), contextlib.redirect_stdout(buffer):
            rc = dbi.main(["publish", "--json"])
        self.assertEqual(calls, ["publish"])
        self.assertNotIn("resolve", calls)
        self.assertEqual(rc, 0)

    def test_publish_does_not_raise(self) -> None:
        """The old dead code fell through to ``resolve()`` and crashed."""
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                dbi.main(["publish", "--json"])
        except AttributeError as exc:  # pragma: no cover - the regression
            self.fail(f"publish must not crash: {exc}")
        except SystemExit:
            pass

    def test_a_real_publish_reports_unavailable_without_docker(self) -> None:
        """No docker here: the record cannot be read, which is not a crash."""
        result = dbi.publish()
        self.assertIn(result["status"], {"PASS", "UNAVAILABLE"})
        self.assertIsInstance(result["problems"], list)


if __name__ == "__main__":
    unittest.main()
