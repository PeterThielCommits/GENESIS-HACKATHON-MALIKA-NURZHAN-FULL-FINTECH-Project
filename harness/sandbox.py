"""Platform-specific process isolation profile and workspace staging (Phase 9, Task 9.8).

Implements Master TZ v3.0.0 §16.2, REQ-SEAL-001..005, P-012, and R-09:
  - Stages a read-only copy of ``public/`` for the ``env`` subprocess in an
    ephemeral directory where ``sealed/``, ``truth.json``, and ``provenance.json``
    physically do not exist (REQ-SEAL-001);
  - Creates a separate empty ephemeral working directory for the ``policy``
    subprocess with zero episode files (REQ-SEAL-002);
  - Constructs a strict allowlisted environment dictionary stripping secrets,
    tokens, seeds, and private paths (REQ-SEAL-004);
  - Applies best-effort POSIX ``resource`` soft limits (``RLIMIT_NOFILE``,
    ``RLIMIT_FSIZE``, ``RLIMIT_CPU``) when supported by the host OS;
  - Emits an honest, machine-readable ``SecurityProfile`` that NEVER claims a
    full OS-level sandbox when only subprocess separation is active (P-012, R-09).

Imports ONLY ``contracts/`` and Python 3.11 stdlib (obeys ``harness/`` boundary).
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import resource as _posix_resource
except ImportError:  # pragma: no cover - non-POSIX fallback
    _posix_resource = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWLISTED_PUBLIC_FILENAMES: frozenset[str] = frozenset(
    {
        "company.json",
        "policy.json",
        "accounts.json",
        "opening_balances.json",
        "period_calendar.json",
        "counterparties.jsonl",
        "fx_rates.jsonl",
        "invoices.jsonl",
        "payments.jsonl",
        "credit_notes.jsonl",
        "bank_lines.jsonl",
        "journal_entries.jsonl",
        "document_links.jsonl",
    }
)

FORBIDDEN_ENV_SUBSTRINGS: tuple[str, ...] = (
    "SECRET",
    "TOKEN",
    "KEY",
    "PASSWORD",
    "CANARY",
    "SALT",
    "SEED",
    "TRUTH",
    "SEALED",
)


@dataclass(frozen=True)
class SecurityProfile:
    """Honest runtime process-isolation capability descriptor (TZ §16.2, P-012)."""

    profile_id: str
    platform_system: str
    platform_release: str
    python_version: str
    running_as_non_root: bool
    inside_container: bool
    is_full_os_sandbox: bool
    enforced_controls: tuple[str, ...]
    unavailable_controls: tuple[str, ...]
    honesty_note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "platform_system": self.platform_system,
            "platform_release": self.platform_release,
            "python_version": self.python_version,
            "running_as_non_root": self.running_as_non_root,
            "inside_container": self.inside_container,
            "is_full_os_sandbox": self.is_full_os_sandbox,
            "enforced_controls": list(self.enforced_controls),
            "unavailable_controls": list(self.unavailable_controls),
            "honesty_note": self.honesty_note,
        }


def _detect_inside_container() -> bool:
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.is_file():
        try:
            txt = cgroup.read_text(encoding="utf-8", errors="ignore")
            if any(k in txt for k in ("docker", "containerd", "kubepods", "lxc")):
                return True
        except OSError:
            pass
    return False


def _detect_non_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if callable(geteuid):
        return int(geteuid()) != 0
    return False


def _probe_posix_rlimits() -> tuple[list[str], list[str]]:
    enforced: list[str] = []
    unavailable: list[str] = []
    if _posix_resource is None:
        return enforced, ["posix_rlimit_cpu", "posix_rlimit_fsize", "posix_rlimit_nofile"]
    for attr, label in (
        ("RLIMIT_CPU", "posix_rlimit_cpu"),
        ("RLIMIT_FSIZE", "posix_rlimit_fsize"),
        ("RLIMIT_NOFILE", "posix_rlimit_nofile"),
    ):
        rlim_id = getattr(_posix_resource, attr, None)
        if rlim_id is None:
            unavailable.append(label)
            continue
        try:
            _posix_resource.getrlimit(rlim_id)
            enforced.append(label)
        except (OSError, ValueError):
            unavailable.append(label)
    return enforced, unavailable


def detect_security_profile() -> SecurityProfile:
    """Inspect current host/container environment and report actual controls honestly."""
    inside_container = _detect_inside_container()
    non_root = _detect_non_root()
    rlim_ok, rlim_missing = _probe_posix_rlimits()

    enforced: list[str] = [
        "separate_os_subprocesses_policy_env_scorer",
        "post_termination_scorer_barrier",
        "ephemeral_empty_policy_cwd_without_episodes",
        "staged_readonly_public_dir_without_sealed",
        "stdin_stdout_jsonl_pipes_only",
        "close_extra_file_descriptors",
        "allowlisted_sanitized_env_vars",
        "fixed_argv_no_shell_interpolation",
        *rlim_ok,
    ]
    if non_root:
        enforced.append("non_root_uid")
    else:
        rlim_missing.append("non_root_uid")

    unavailable: list[str] = list(rlim_missing)
    if not inside_container:
        unavailable.extend(
            [
                "container_mount_namespace",
                "container_network_disabled_flag",
                "seccomp_bpf_syscall_filter",
            ]
        )
    else:
        # Even inside a container, inner subprocesses share the container's
        # filesystem namespace unless separate containers/namespaces are used.
        unavailable.append("per_subprocess_user_mount_namespace")

    profile_id = (
        "container-posix-subprocess-v1"
        if inside_container
        else "host-posix-subprocess-v1"
    )
    honesty_note = (
        "Process separation, empty scratch cwd, read-only public staging without "
        "sealed files, FD closure, sanitized env allowlist, and POSIX soft rlimits "
        "are enforced. Plain OS subprocesses do NOT constitute a kernel-level "
        "mandatory-access-control sandbox without outer Docker (--network=none, "
        "unmounted sealed volumes, non-root UID) enforcement."
    )
    return SecurityProfile(
        profile_id=profile_id,
        platform_system=platform.system(),
        platform_release=platform.release(),
        python_version=sys.version.split()[0],
        running_as_non_root=non_root,
        inside_container=inside_container,
        is_full_os_sandbox=False,
        enforced_controls=tuple(enforced),
        unavailable_controls=tuple(unavailable),
        honesty_note=honesty_note,
    )


def build_sanitized_env(
    *,
    role: str,
    include_repo_pythonpath: bool = True,
    extra_pythonpath: Path | None = None,
) -> dict[str, str]:
    """Construct a strict allowlisted environment dictionary (REQ-SEAL-004).

    Never forwards host environment variables that could carry secrets, tokens,
    seeds, salts, canary strings, or episode paths.
    """
    if role not in ("POLICY", "ENV", "SCORER"):
        raise ValueError(f"unsupported process role: {role!r}")

    raw_path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    env: dict[str, str] = {
        "PATH": raw_path,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "TWINLEDGER_PROCESS_ROLE": role,
    }
    py_paths: list[str] = []
    if extra_pythonpath is not None:
        py_paths.append(str(extra_pythonpath.resolve()))
    if include_repo_pythonpath:
        py_paths.append(str(REPO_ROOT))
    if py_paths:
        env["PYTHONPATH"] = os.pathsep.join(py_paths)

    # Defensive assertion: ensure no forbidden token leaked into keys
    for key in list(env.keys()):
        upper_key = key.upper()
        if any(tok in upper_key for tok in FORBIDDEN_ENV_SUBSTRINGS):
            del env[key]
    return env


def make_posix_preexec(
    *,
    cpu_seconds: int = 65,
    max_fsize_bytes: int = 32 * 1024 * 1024,
    max_nofile: int = 128,
) -> Callable[[], None] | None:
    """Return a child-process ``preexec_fn`` applying safe POSIX soft rlimits."""
    if os.name != "posix" or _posix_resource is None:
        return None

    def _apply_limits() -> None:
        assert _posix_resource is not None
        # Apply soft limits without raising hard limits (never fails if soft <= hard)
        for attr, desired in (
            ("RLIMIT_CPU", cpu_seconds),
            ("RLIMIT_FSIZE", max_fsize_bytes),
            ("RLIMIT_NOFILE", max_nofile),
        ):
            rlim_id = getattr(_posix_resource, attr, None)
            if rlim_id is None:
                continue
            try:
                soft, hard = _posix_resource.getrlimit(rlim_id)
                if hard != _posix_resource.RLIM_INFINITY:
                    target_soft = min(desired, hard)
                else:
                    target_soft = desired
                if soft == _posix_resource.RLIM_INFINITY or target_soft < soft:
                    _posix_resource.setrlimit(rlim_id, (target_soft, hard))
            except (OSError, ValueError):
                pass

    return _apply_limits


def _make_tree_writable_for_cleanup(root: Path) -> None:
    if not root.exists():
        return
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        try:
            os.chmod(dp, stat.S_IRWXU)
        except OSError:
            pass
        for dn in dirnames:
            try:
                os.chmod(dp / dn, stat.S_IRWXU)
            except OSError:
                pass
        for fn in filenames:
            try:
                os.chmod(dp / fn, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass


class StagedPublicWorkspace:
    """Ephemeral read-only ``public/`` workspace for ``env`` subprocess (REQ-SEAL-001).

    Copies ONLY allowlisted regular files from ``<episode_dir>/public/`` into a
    fresh temporary directory, marks all files ``0o444`` and directories ``0o555``,
    and guarantees that ``sealed/``, ``truth.json``, and ``provenance.json`` do
    not exist anywhere inside the workspace.
    """

    def __init__(self, source_public_dir: Path | str) -> None:
        self._source_public = Path(source_public_dir)
        self._root_dir: Path | None = None
        self._staged_public_dir: Path | None = None

    @property
    def root_dir(self) -> Path:
        if self._root_dir is None:
            raise RuntimeError("StagedPublicWorkspace is not active")
        return self._root_dir

    @property
    def public_dir(self) -> Path:
        if self._staged_public_dir is None:
            raise RuntimeError("StagedPublicWorkspace is not active")
        return self._staged_public_dir

    def __enter__(self) -> "StagedPublicWorkspace":
        if not self._source_public.is_dir() or self._source_public.is_symlink():
            raise ValueError(f"invalid source public directory: {self._source_public}")
        src_resolved = self._source_public.resolve()

        tmp_root = Path(tempfile.mkdtemp(prefix="tl_env_pub_"))
        staged_pub = tmp_root / "public"
        staged_pub.mkdir(mode=0o700)

        try:
            for entry in sorted(self._source_public.iterdir(), key=lambda p: p.name):
                if entry.name.startswith("."):
                    raise ValueError(f"dotfile forbidden in public/: {entry.name}")
                if entry.is_symlink():
                    raise ValueError(f"symlink forbidden in public/: {entry.name}")
                if entry.name not in ALLOWLISTED_PUBLIC_FILENAMES:
                    raise ValueError(f"unlisted file forbidden in public/: {entry.name}")
                resolved_file = entry.resolve()
                if not resolved_file.is_relative_to(src_resolved) or not entry.is_file():
                    raise ValueError(f"non-regular file forbidden in public/: {entry.name}")

                dest = staged_pub / entry.name
                shutil.copyfile(resolved_file, dest)
                os.chmod(dest, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444

            # Lock directories read-only + traverse (0o555)
            os.chmod(staged_pub, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            os.chmod(tmp_root, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        except Exception:
            _make_tree_writable_for_cleanup(tmp_root)
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise

        self._root_dir = tmp_root
        self._staged_public_dir = staged_pub
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._root_dir is not None:
            _make_tree_writable_for_cleanup(self._root_dir)
            shutil.rmtree(self._root_dir, ignore_errors=True)
            self._root_dir = None
            self._staged_public_dir = None


class IsolatedPolicyWorkspace:
    """Empty ephemeral working directory for external ``policy`` subprocess (REQ-SEAL-002)."""

    def __init__(self) -> None:
        self._cwd: Path | None = None

    @property
    def cwd(self) -> Path:
        if self._cwd is None:
            raise RuntimeError("IsolatedPolicyWorkspace is not active")
        return self._cwd

    def __enter__(self) -> "IsolatedPolicyWorkspace":
        tmp_dir = Path(tempfile.mkdtemp(prefix="tl_policy_cwd_"))
        # Read + execute only (0o555) so policy cannot even drop persistent files in cwd
        os.chmod(tmp_dir, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        self._cwd = tmp_dir
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._cwd is not None:
            _make_tree_writable_for_cleanup(self._cwd)
            shutil.rmtree(self._cwd, ignore_errors=True)
            self._cwd = None


__all__ = [
    "ALLOWLISTED_PUBLIC_FILENAMES",
    "IsolatedPolicyWorkspace",
    "SecurityProfile",
    "StagedPublicWorkspace",
    "build_sanitized_env",
    "detect_security_profile",
    "make_posix_preexec",
]
