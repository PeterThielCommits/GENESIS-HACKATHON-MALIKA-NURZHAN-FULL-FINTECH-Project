"""Platform-specific process isolation profile & workspace sandboxing (Phase 9/16).

Implements Master TZ §16.2, Principle P-012, and Risk R-09:
- When running on Linux with unprivileged user/mount/network namespaces +
  ``seccomp-BPF`` available (verified via a live self-test probe at startup),
  enforces **full kernel-level OS sandboxing** via ``harness/ns_launcher.py``:
  - Private mount namespace (``MS_REC | MS_PRIVATE``) masking ``episodes/`` and
    active ``episode_dir`` with read-only ``tmpfs`` so ``sealed/`` is invisible
    even if a child process knows exact absolute host paths;
  - Isolated network namespace (``unshare --net``) with no external interfaces;
  - ``PR_SET_NO_NEW_PRIVS = 1``;
  - Irreversible ``seccomp-BPF`` syscall filter blocking ``socket``, ``mount``,
    ``umount2``, ``pivot_root``, ``ptrace``, ``process_vm_readv``, and
    ``process_vm_writev`` with ``EPERM``;
- Also enforces defence-in-depth POSIX subprocess controls on all platforms:
  - Separate empty read-only ``cwd`` for ``policy``;
  - Staged read-only ``public/`` workspace for ``env`` (12 allowlisted public
    files only; zero ``sealed/``);
  - ``close_fds=True``, sanitized env allowlist, fixed ``argv`` (``shell=False``),
    and POSIX soft ``RLIMIT_CPU`` / ``RLIMIT_FSIZE`` / ``RLIMIT_NOFILE``.
- Reports ``is_full_os_sandbox = True`` ONLY when live-probed kernel mount +
  network + seccomp-BPF controls are verified active; otherwise reports
  ``is_full_os_sandbox = False`` and lists unavailable kernel controls honestly.

Zone 2 rule: imports ONLY ``contracts`` and Python 3.11 stdlib.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    import resource as _posix_resource
except ImportError:  # pragma: no cover
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
    }
)

SAFE_BASE_ENV_VARS: tuple[str, ...] = (
    "PATH",
    "LANG",
    "LC_ALL",
    "SYSTEMROOT",
    "TZ",
)

FORBIDDEN_ENV_SUBSTRINGS: tuple[str, ...] = (
    "SECRET",
    "TOKEN",
    "KEY",
    "PASS",
    "SALT",
    "CANARY",
    "SEED",
    "TRUTH",
    "SEALED",
)


@dataclass(frozen=True)
class KernelSandboxCapabilities:
    """Result of live startup probe of kernel namespace + seccomp-BPF isolation."""

    available: bool
    unshare_bin: str | None
    mount_namespace_verified: bool
    net_namespace_verified: bool
    seccomp_bpf_verified: bool
    probe_detail: str


_CACHED_KERNEL_CAPS: KernelSandboxCapabilities | None = None


def probe_kernel_sandbox_capabilities(*, force_refresh: bool = False) -> KernelSandboxCapabilities:
    """Run a 1-shot live child probe verifying Linux user+mount+net+seccomp isolation."""
    global _CACHED_KERNEL_CAPS
    if _CACHED_KERNEL_CAPS is not None and not force_refresh:
        return _CACHED_KERNEL_CAPS

    if platform.system() != "Linux":
        _CACHED_KERNEL_CAPS = KernelSandboxCapabilities(
            available=False,
            unshare_bin=None,
            mount_namespace_verified=False,
            net_namespace_verified=False,
            seccomp_bpf_verified=False,
            probe_detail="non-Linux platform",
        )
        return _CACHED_KERNEL_CAPS

    unshare_bin = shutil.which("unshare")
    if not unshare_bin:
        _CACHED_KERNEL_CAPS = KernelSandboxCapabilities(
            available=False,
            unshare_bin=None,
            mount_namespace_verified=False,
            net_namespace_verified=False,
            seccomp_bpf_verified=False,
            probe_detail="unshare binary not found",
        )
        return _CACHED_KERNEL_CAPS

    try:
        with tempfile.TemporaryDirectory(prefix="tl_kprobe_") as td:
            sec_dir = Path(td) / "sealed_probe"
            sec_dir.mkdir()
            secret_file = sec_dir / "truth.json"
            secret_file.write_text("probe", encoding="utf-8")

            probe_code = (
                "import ctypes, ctypes.util, os, socket, sys\n"
                f"masked_ok = not os.path.exists({str(secret_file)!r})\n"
                "net_blocked = False\n"
                "try:\n"
                "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
                "    s.close()\n"
                "except OSError:\n"
                "    net_blocked = True\n"
                "libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6', use_errno=True)\n"
                f"rc = libc.umount2({os.fsencode(str(sec_dir.resolve()))!r}, 2)\n"
                "seccomp_ok = (rc == -1 and ctypes.get_errno() == 1)\n"
                "print(f'{int(masked_ok)}|{int(net_blocked)}|{int(seccomp_ok)}')\n"
            )
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "PYTHONPATH": str(REPO_ROOT),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            cmd = [
                unshare_bin,
                "--user",
                "--map-root-user",
                "--net",
                "--mount",
                "--",
                sys.executable,
                "-m",
                "harness.ns_launcher",
                "--mask-dir",
                str(sec_dir),
                "--",
                sys.executable,
                "-c",
                probe_code,
            ]
            proc = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=5.0,
                close_fds=True,
            )
            if proc.returncode == 0:
                parts = proc.stdout.strip().split("|")
                if len(parts) == 3:
                    m_ok = parts[0] == "1"
                    n_ok = parts[1] == "1"
                    s_ok = parts[2] == "1"
                    all_ok = m_ok and n_ok and s_ok
                    _CACHED_KERNEL_CAPS = KernelSandboxCapabilities(
                        available=all_ok,
                        unshare_bin=unshare_bin,
                        mount_namespace_verified=m_ok,
                        net_namespace_verified=n_ok,
                        seccomp_bpf_verified=s_ok,
                        probe_detail="verified via live unshare+tmpfs+seccomp self-test",
                    )
                    return _CACHED_KERNEL_CAPS
            detail = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()[:160]
    except Exception as exc:
        detail = str(exc)[:160]

    _CACHED_KERNEL_CAPS = KernelSandboxCapabilities(
        available=False,
        unshare_bin=unshare_bin,
        mount_namespace_verified=False,
        net_namespace_verified=False,
        seccomp_bpf_verified=False,
        probe_detail=detail,
    )
    return _CACHED_KERNEL_CAPS


def wrap_argv_with_kernel_sandbox(
    target_argv: Sequence[str],
    *,
    mask_dirs: Sequence[Path | str] = (),
    chdir: Path | str | None = None,
    readonly_chdir: bool = False,
) -> tuple[list[str], bool]:
    """Wrap ``target_argv`` in ``unshare`` + ``harness.ns_launcher`` when supported.

    Returns ``(effective_argv, kernel_sandbox_active)``. Automatically masks
    ``REPO_ROOT / 'episodes'`` plus all caller-provided ``mask_dirs``.
    """
    caps = probe_kernel_sandbox_capabilities()
    if not caps.available or not caps.unshare_bin:
        return [str(x) for x in target_argv], False

    cmd: list[str] = [
        caps.unshare_bin,
        "--user",
        "--map-root-user",
        "--net",
        "--mount",
        "--",
        sys.executable,
        "-m",
        "harness.ns_launcher",
    ]
    default_episodes_dir = REPO_ROOT / "episodes"
    all_masks: list[str] = []
    if default_episodes_dir.is_dir():
        all_masks.append(str(default_episodes_dir.resolve()))
    for d in mask_dirs:
        p = Path(d)
        if p.is_dir():
            resolved = str(p.resolve())
            if resolved not in all_masks:
                all_masks.append(resolved)
    for m in all_masks:
        cmd.extend(["--mask-dir", m])
    if chdir is not None:
        cmd.extend(["--chdir", str(Path(chdir).resolve())])
    if readonly_chdir:
        cmd.append("--readonly-chdir")
    cmd.append("--")
    cmd.extend(str(x) for x in target_argv)
    return cmd, True


@dataclass(frozen=True)
class SecurityProfile:
    """Explicit, non-exaggerated record of active OS/process isolation controls."""

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


def detect_security_profile(*, force_non_kernel: bool = False) -> SecurityProfile:
    """Inspect current runtime and return an accurate ``SecurityProfile``."""
    sys_name = platform.system()
    rel = platform.release()
    py_ver = sys.version.split()[0]
    non_root = hasattr(os, "geteuid") and os.geteuid() != 0
    in_container = Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()
    caps = (
        KernelSandboxCapabilities(False, None, False, False, False, "forced_non_kernel")
        if force_non_kernel
        else probe_kernel_sandbox_capabilities()
    )

    enforced: list[str] = [
        "separate_os_subprocesses_policy_env_scorer",
        "post_termination_scorer_barrier",
        "ephemeral_empty_policy_cwd_without_episodes",
        "staged_readonly_public_dir_without_sealed",
        "stdin_stdout_jsonl_pipes_only",
        "close_extra_file_descriptors",
        "allowlisted_sanitized_env_vars",
        "fixed_argv_no_shell_interpolation",
    ]
    unavailable: list[str] = []

    if _posix_resource is not None:
        enforced.extend(
            [
                "posix_rlimit_cpu",
                "posix_rlimit_fsize",
                "posix_rlimit_nofile",
            ]
        )
    else:
        unavailable.append("posix_rlimits")

    if non_root:
        enforced.append("non_root_uid")
    else:
        unavailable.append("non_root_uid")

    if caps.available:
        enforced.extend(
            [
                "linux_user_mount_namespace_masked_sealed_tmpfs",
                "linux_net_namespace_offline",
                "prctl_no_new_privs",
                "seccomp_bpf_syscall_filter",
            ]
        )
        profile_id = "linux-kernel-ns-seccomp-v1"
        full_sandbox = True
        note = (
            "Live-verified Linux user+mount+network namespaces and seccomp-BPF filter are "
            "enforced: episodes/ and sealed/ paths are masked with read-only tmpfs inside "
            "private mount namespaces, outbound network namespace is isolated, PR_SET_NO_NEW_PRIVS "
            "is set, and seccomp-BPF blocks socket/mount/umount2/pivot_root/ptrace/process_vm_*."
        )
    else:
        if in_container:
            enforced.append("container_filesystem_boundary")
        else:
            unavailable.append("linux_user_mount_namespace_masked_sealed_tmpfs")
        unavailable.extend(
            [
                "linux_net_namespace_offline",
                "seccomp_bpf_syscall_filter",
            ]
        )
        profile_id = "container-posix-subprocess-v1" if in_container else "host-posix-subprocess-v1"
        full_sandbox = False
        note = (
            "Process separation, empty scratch cwd, read-only public staging without sealed files, "
            "FD closure, sanitized env allowlist, and POSIX soft rlimits are enforced. Kernel "
            f"namespace/seccomp probe unavailable ({caps.probe_detail}); use outer Docker "
            "(--network=none, unmounted sealed volumes, non-root UID) for kernel-level isolation."
        )

    return SecurityProfile(
        profile_id=profile_id,
        platform_system=sys_name,
        platform_release=rel,
        python_version=py_ver,
        running_as_non_root=non_root,
        inside_container=in_container,
        is_full_os_sandbox=full_sandbox,
        enforced_controls=tuple(enforced),
        unavailable_controls=tuple(unavailable),
        honesty_note=note,
    )


def build_sanitized_env(
    *,
    role: str,
    include_repo_pythonpath: bool = True,
    extra_pythonpath: Path | None = None,
    extra_allowlisted: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Construct a minimal, secret-free environment dictionary for a subprocess."""
    if role not in ("POLICY", "ENV", "SCORER"):
        raise ValueError(f"unknown process role: {role!r}")

    env: dict[str, str] = {
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONNOUSERSITE": "1",
        "TWINLEDGER_PROCESS_ROLE": role,
    }
    for key in SAFE_BASE_ENV_VARS:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val

    py_paths: list[str] = []
    if extra_pythonpath is not None:
        py_paths.append(str(Path(extra_pythonpath).resolve()))
    if include_repo_pythonpath:
        py_paths.append(str(REPO_ROOT.resolve()))
    if py_paths:
        env["PYTHONPATH"] = os.pathsep.join(py_paths)

    if extra_allowlisted:
        for k, v in extra_allowlisted.items():
            upper = k.upper()
            if any(bad in upper for bad in FORBIDDEN_ENV_SUBSTRINGS):
                raise ValueError(f"refusing to pass forbidden env variable name {k!r}")
            env[str(k)] = str(v)

    for k in list(env.keys()):
        upper = k.upper()
        if k != "TWINLEDGER_PROCESS_ROLE" and any(bad in upper for bad in FORBIDDEN_ENV_SUBSTRINGS):
            del env[k]

    return env


def make_posix_preexec(
    *,
    cpu_seconds: int = 30,
    max_file_bytes: int = 16 * 1024 * 1024,
    max_open_files: int = 128,
) -> Callable[[], None] | None:
    """Return a ``preexec_fn`` applying soft POSIX ``rlimit`` caps where supported."""
    if _posix_resource is None or os.name != "posix":
        return None

    def _apply() -> None:
        for res_attr, soft_val in (
            ("RLIMIT_CPU", cpu_seconds),
            ("RLIMIT_FSIZE", max_file_bytes),
            ("RLIMIT_NOFILE", max_open_files),
        ):
            res_id = getattr(_posix_resource, res_attr, None)
            if res_id is None:
                continue
            try:
                _soft, hard = _posix_resource.getrlimit(res_id)
                effective_soft = soft_val if hard == _posix_resource.RLIM_INFINITY else min(soft_val, hard)
                _posix_resource.setrlimit(res_id, (effective_soft, hard))
            except (ValueError, OSError):
                pass

    return _apply


class StagedPublicWorkspace:
    """Context manager staging ONLY allowlisted ``public/`` files read-only."""

    def __init__(self, source_public_dir: Path | str) -> None:
        self._source_public_dir = Path(source_public_dir).resolve()
        self._tmp_obj: tempfile.TemporaryDirectory[str] | None = None
        self.root_dir: Path | None = None
        self.public_dir: Path | None = None

    def __enter__(self) -> "StagedPublicWorkspace":
        if not self._source_public_dir.is_dir():
            raise FileNotFoundError(f"public episode dir not found: {self._source_public_dir}")

        for entry in sorted(self._source_public_dir.iterdir()):
            if entry.name.startswith("."):
                raise ValueError(f"hidden file forbidden in public dir: {entry.name}")
            if entry.is_symlink():
                raise ValueError(f"symlink forbidden in public dir: {entry.name}")
            if not entry.is_file():
                raise ValueError(f"non-regular file forbidden in public dir: {entry.name}")
            if entry.name not in ALLOWLISTED_PUBLIC_FILENAMES:
                raise ValueError(f"non-allowlisted file in public dir: {entry.name}")

        self._tmp_obj = tempfile.TemporaryDirectory(prefix="tl_public_")
        self.root_dir = Path(self._tmp_obj.name).resolve()
        self.public_dir = self.root_dir / "public"
        self.public_dir.mkdir(mode=0o755)

        for filename in sorted(ALLOWLISTED_PUBLIC_FILENAMES):
            src = self._source_public_dir / filename
            if not src.is_file():
                self._cleanup()
                raise FileNotFoundError(f"missing required public file: {filename}")
            dst = self.public_dir / filename
            shutil.copyfile(src, dst, follow_symlinks=False)
            os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444

        os.chmod(self.public_dir, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)  # 0o550
        os.chmod(self.root_dir, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)  # 0o550
        return self

    def _cleanup(self) -> None:
        if self.root_dir is not None and self.root_dir.exists():
            try:
                os.chmod(self.root_dir, 0o700)
                if self.public_dir is not None and self.public_dir.exists():
                    os.chmod(self.public_dir, 0o700)
                    for child in self.public_dir.iterdir():
                        try:
                            os.chmod(child, 0o600)
                        except OSError:
                            pass
            except OSError:
                pass
        if self._tmp_obj is not None:
            self._tmp_obj.cleanup()
            self._tmp_obj = None

    def cleanup(self) -> None:
        self._cleanup()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._cleanup()


class IsolatedPolicyWorkspace:
    """Context manager creating an empty scratch directory for ``policy`` subprocess."""

    def __init__(self) -> None:
        self._tmp_obj: tempfile.TemporaryDirectory[str] | None = None
        self.cwd: Path | None = None

    def __enter__(self) -> Path:
        self._tmp_obj = tempfile.TemporaryDirectory(prefix="tl_policy_cwd_")
        self.cwd = Path(self._tmp_obj.name).resolve()
        os.chmod(self.cwd, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP)  # 0o550
        return self.cwd

    def cleanup(self) -> None:
        if self.cwd is not None and self.cwd.exists():
            try:
                os.chmod(self.cwd, 0o700)
            except OSError:
                pass
        if self._tmp_obj is not None:
            self._tmp_obj.cleanup()
            self._tmp_obj = None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()


__all__ = [
    "ALLOWLISTED_PUBLIC_FILENAMES",
    "FORBIDDEN_ENV_SUBSTRINGS",
    "IsolatedPolicyWorkspace",
    "KernelSandboxCapabilities",
    "REPO_ROOT",
    "SAFE_BASE_ENV_VARS",
    "SecurityProfile",
    "StagedPublicWorkspace",
    "build_sanitized_env",
    "detect_security_profile",
    "make_posix_preexec",
    "probe_kernel_sandbox_capabilities",
    "wrap_argv_with_kernel_sandbox",
]
