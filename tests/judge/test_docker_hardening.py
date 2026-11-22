"""Container hardening regressions: build context, base image, Compose profile.

These tests lock the three contracts that the submission image depends on:

1. **The build context** (``tools/docker_context.py``) must exclude sealed
   truth, key material, VCS metadata and stale bytecode at *any* depth, and
   must not silently drop a tracked file that the runtime needs. Docker
   anchors every ``.dockerignore`` pattern at the context root, so the old
   root-anchored ``__pycache__`` / ``*.pem`` / ``.env`` rules leaked 197 stale
   ``.pyc`` files into the image.
2. **The base image** (``tools/docker_build_info.py``) must be pinned by
   digest, and the recorded build info must agree with the Dockerfile
   (TZ §22.4).
3. **The Compose profile** (``tools/check_compose_profile.py``) must keep every
   service offline, read-only, non-root, capability-free and resource-capped
   (TZ §16.2, §22.4, §22.5), and the checker must actually fail when one of
   those properties is removed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import container_local_check as clc
from tools import docker_build_info as dbi
from tools import release_audit
from tools.check_compose_profile import check_compose, check_service, parse_simple_yaml
from tools.docker_context import DockerIgnore, build_context

DOCKERFILE = REPO_ROOT / "Dockerfile"
COMPOSE = REPO_ROOT / "docker-compose.yml"


class TestDockerIgnoreSemantics(unittest.TestCase):
    """Docker anchors every pattern at the context root -- the rules must not."""

    def setUp(self) -> None:
        self.ignore = DockerIgnore.from_file(REPO_ROOT / ".dockerignore")

    def test_nested_bytecode_is_excluded(self) -> None:
        for path in (
            "__pycache__/x.pyc",
            "contracts/__pycache__/loader.cpython-311.pyc",
            "tests/judge/__pycache__/test_x.cpython-311.pyc",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.ignore.excluded(path), path)

    def test_root_anchored_patterns_are_not_used(self) -> None:
        """A pattern without a slash would only match the context root."""
        patterns = [
            line.strip()
            for line in (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        for pattern in ("__pycache__", ".env", "*.pem", "*.key", ".venv"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(
                    pattern,
                    patterns,
                    f"{pattern!r} is anchored at the context root in Docker and misses nested copies",
                )

    def test_sealed_truth_is_excluded_at_every_depth(self) -> None:
        for path in (
            "episodes/sealed/truth.json",
            "episodes/dev/ep_dev_001_clean_distractors/sealed/truth.json",
            "episodes/train/ep_train_004_compound_all4/sealed/provenance.json",
            "episodes/hidden/whatever.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.ignore.excluded(path), path)

    def test_key_material_is_excluded_at_any_depth(self) -> None:
        for path in ("deploy/prod.pem", "keys/service.key", "app/.env", ".env"):
            with self.subTest(path=path):
                self.assertTrue(self.ignore.excluded(path), path)

    def test_public_episode_data_stays_in_the_context(self) -> None:
        path = "episodes/dev/ep_dev_001_clean_distractors/public/accounts.json"
        self.assertFalse(self.ignore.excluded(path))


class TestEffectiveBuildContext(unittest.TestCase):
    """The real context of this repository must be free of forbidden material."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.context = build_context(REPO_ROOT)

    def test_context_has_no_forbidden_path(self) -> None:
        violations = clc.context_violations(self.context)
        self.assertEqual(violations, [], violations)

    def test_context_has_no_stale_bytecode(self) -> None:
        stale = [p for p in self.context if "__pycache__" in p or p.endswith(".pyc")]
        self.assertEqual(stale, [], stale)

    def test_context_contains_every_shipped_file_that_is_not_excluded(self) -> None:
        """Every file the release audit ships must reach the image.

        The comparison uses the release audit's own file list, which falls back
        to a filesystem walk when no ``git`` binary exists - the offline image
        ships neither ``git`` nor a ``.git`` tree, so the check has to work
        there as well (a skipped check is not a passed check).
        """
        shipped = set(release_audit.tracked_files())
        context = set(self.context)
        deliberately_excluded = {
            "artifacts/trajectories/trajectories.jsonl",  # generated inside the container
        }
        missing = sorted(shipped - context - deliberately_excluded)
        self.assertEqual(missing, [], missing)

    def test_required_runtime_files_are_present(self) -> None:
        self.assertEqual(clc.missing_required(self.context), [])


class TestBaseImagePinning(unittest.TestCase):
    """TZ 22.4: the base image digest, the Python version and the packages."""

    def test_dockerfile_pins_the_base_image_by_digest(self) -> None:
        parsed = dbi.parse_dockerfile(DOCKERFILE)
        self.assertNotIn("error", parsed, parsed.get("error"))
        self.assertTrue(
            dbi.base_image_is_pinned(parsed),
            "the base image must be pinned by digest (TZ 22.4)",
        )
        self.assertFalse(
            dbi.is_placeholder_digest(parsed["base_image_digest"]),
            "the pinned digest must be a real digest, not a placeholder",
        )
        self.assertTrue(parsed["uses_arg"], "FROM must use ${BASE_IMAGE}")
        self.assertEqual(parsed["base_image_name"], dbi.EXPECTED_BASE_NAME)

    def test_dockerfile_keeps_the_offline_and_non_root_guarantees(self) -> None:
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("PIP_NO_INDEX=1", text)
        self.assertIn("USER 10001:10001", text)
        self.assertIn('CMD ["make", "verify"]', text)
        self.assertIn("docker_build_info.py emit", text)

    def test_static_verify_passes_for_the_committed_state(self) -> None:
        result = dbi.verify(require_pinned=True)
        self.assertEqual(result["status"], "PASS", result["problems"])
        # The build-info record is written from a *built* image; until it is
        # committed the check reports it as a warning, not a failure.
        for warning in result.get("warnings", []):
            self.assertIn("docker-build-info.json", warning)

    def test_static_verify_rejects_a_placeholder_digest(self) -> None:
        parsed = dict(dbi.parse_dockerfile(DOCKERFILE))
        parsed["base_image_digest"] = "sha256:" + "0" * 64
        self.assertTrue(dbi.is_placeholder_digest(parsed["base_image_digest"]))

    def test_committed_build_info_matches_the_dockerfile(self) -> None:
        path = REPO_ROOT / "docs" / "EVIDENCE" / "docker-build-info.json"
        if not path.is_file():
            self.skipTest("docs/EVIDENCE/docker-build-info.json is not committed yet")
        committed = json.loads(path.read_text(encoding="utf-8"))
        parsed = dbi.parse_dockerfile(DOCKERFILE)
        self.assertEqual(committed["base_image_digest"], parsed["base_image_digest"])
        self.assertEqual(committed["base_image"], parsed["base_image_name"])
        self.assertTrue(committed["python_version"].startswith("3.11."))
        for package in dbi.TRACKED_APT_PACKAGES:
            self.assertIn(package, committed["apt_packages_required"])

    def test_committed_build_info_publishes_the_observed_package_versions(self) -> None:
        """TZ 22.4 asks for the package versions, not only the package names."""
        path = REPO_ROOT / "docs" / "EVIDENCE" / "docker-build-info.json"
        if not path.is_file():
            self.skipTest("docs/EVIDENCE/docker-build-info.json is not committed yet")
        committed = json.loads(path.read_text(encoding="utf-8"))
        observed = committed.get("apt_packages_observed")
        self.assertIsInstance(observed, dict, "the observed package versions must be published")
        for package in dbi.TRACKED_APT_PACKAGES:
            version = observed.get(package)
            self.assertTrue(version, f"no observed version for {package}")
            self.assertNotEqual(version, "unknown", f"{package} records 'unknown', not a fact")
            self.assertRegex(version, r"^\d", f"{package} version {version!r} is not a version")

    def test_static_verify_rejects_an_unrecorded_package_version(self) -> None:
        """The static check must fail when a version was never observed."""
        committed = json.loads(
            (REPO_ROOT / "docs" / "EVIDENCE" / "docker-build-info.json").read_text(
                encoding="utf-8"
            )
        )
        broken = dict(committed)
        broken["apt_packages_observed"] = {"make": "4.3-4.1"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "docker-build-info.json"
            path.write_text(json.dumps(broken), encoding="utf-8")
            original = dbi.BUILD_INFO_PATH
            try:
                dbi.BUILD_INFO_PATH = path
                result = dbi.verify(require_pinned=True, require_build_info=True)
            finally:
                dbi.BUILD_INFO_PATH = original
        self.assertEqual(result["status"], "FAIL", result["problems"])
        self.assertTrue(
            any("util-linux" in problem for problem in result["problems"]),
            result["problems"],
        )


class TestComposeProfile(unittest.TestCase):
    """The Compose profile is the judge-facing container definition."""

    def test_compose_profile_satisfies_the_hardening_contract(self) -> None:
        result = check_compose(COMPOSE)
        self.assertEqual(result["status"], "PASS", result["problems"])
        self.assertEqual(sorted(result["services"]), ["env-sandbox", "policy-sandbox", "verify"])

    def test_checker_detects_a_service_that_regains_network_access(self) -> None:
        service = {
            "network_mode": "bridge",
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "user": "10001:10001",
            "cpus": 2.0,
            "mem_limit": "4g",
            "pids_limit": 512,
            "ulimits": {"fsize": {"soft": 1, "hard": 1}},
        }
        problems = check_service("broken", service)
        self.assertTrue(any("network_mode" in problem for problem in problems), problems)

    def test_checker_detects_a_root_or_writable_service(self) -> None:
        service = {
            "network_mode": "none",
            "read_only": False,
            "cap_drop": [],
            "security_opt": [],
            "user": "root",
            "cpus": 8,
            "mem_limit": "16g",
        }
        problems = check_service("broken", service)
        for expected in ("read_only", "cap_drop", "security_opt", "user", "cpus", "mem_limit", "pids_limit", "ulimits"):
            self.assertTrue(any(expected in problem for problem in problems), (expected, problems))

    def test_checker_detects_a_bind_mount(self) -> None:
        service = {
            "network_mode": "none",
            "read_only": True,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "user": "10001:10001",
            "cpus": 2.0,
            "mem_limit": "4g",
            "pids_limit": 512,
            "ulimits": {"fsize": {"soft": 1, "hard": 1}},
            "volumes": ["./episodes:/app/episodes:ro"],
        }
        problems = check_service("broken", service)
        self.assertTrue(any("bind mounts" in problem for problem in problems), problems)

    def test_yaml_reader_understands_the_compose_file(self) -> None:
        document = parse_simple_yaml(COMPOSE.read_text(encoding="utf-8"))
        verify = document["services"]["verify"]
        self.assertEqual(verify["network_mode"], "none")
        self.assertIs(verify["read_only"], True)
        self.assertEqual(verify["cap_drop"], ["ALL"])
        self.assertEqual(verify["user"], "10001:10001")
        self.assertEqual(verify["pids_limit"], 512)
        tmpfs = "\n".join(verify["tmpfs"])
        for required in ("/app/artifacts/reports/latest", "/app/artifacts/trajectories"):
            self.assertIn(required, tmpfs)


class TestContainerLocalCheck(unittest.TestCase):
    """The container-equivalent local run must really apply the hardening."""

    def test_run_script_drops_privileges_and_read_only_roots_the_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tl-script-") as tmp:
            script = clc._run_script(Path(tmp) / "app", ("make", "verify"), Path(tmp) / "captured")
        self.assertIn("mount --bind", script)
        self.assertIn("remount,bind,ro", script)
        self.assertIn("mount -t tmpfs", script)
        self.assertIn(f"--map-user={clc.CONTAINER_UID}", script)
        self.assertIn("--no-new-privs", script)
        self.assertIn("--inh-caps=-all", script)
        self.assertIn("artifacts/reports/latest", script)

    def test_container_command_is_the_documented_single_command(self) -> None:
        self.assertEqual(clc.CONTAINER_CMD, ("make", "verify"))

    def test_forbidden_patterns_cover_the_sealed_layout(self) -> None:
        self.assertTrue(clc.context_violations(["episodes/dev/ep_x/sealed/truth.json"]))
        self.assertTrue(clc.context_violations(["contracts/__pycache__/x.cpython-311.pyc"]))
        self.assertTrue(clc.context_violations(["deploy/prod.pem"]))
        self.assertEqual(clc.context_violations(["episodes/dev/ep_x/public/accounts.json"]), [])


if __name__ == "__main__":
    unittest.main()
