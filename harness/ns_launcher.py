"""Linux kernel user+mount+network namespace + seccomp-BPF launcher.

Invoked inside ``unshare --user --map-root-user --net --mount`` with fixed
``argv`` (never ``shell=True``). Before ``os.execv`` into the target Python
process (``policy`` or ``env``):
  1. Sets ``/`` mount propagation to ``MS_REC | MS_PRIVATE`` so mounts never
     leak back to the host namespace.
  2. Overmounts every ``--mask-dir`` path (e.g., ``episodes/``, ``episode_dir``)
     with a read-only ``tmpfs`` (``MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC``),
     hiding sealed files at the Linux kernel VFS layer even if a hostile process
     knows exact absolute host paths.
  3. Sets ``PR_SET_NO_NEW_PRIVS = 1`` via ``libc.prctl``.
  4. Installs an irreversible ``seccomp-BPF`` filter (``x86_64`` and ``aarch64``)
     returning ``EPERM`` on ``socket``, ``ptrace``, ``process_vm_readv``,
     ``process_vm_writev``, ``mount``, ``umount2``, and ``pivot_root`` so the
     child process can neither unmount the ``tmpfs`` masks, attach debuggers,
     nor create network sockets.
  5. Optionally changes directory to ``--chdir`` and ``os.execv``s into the
     target executable.

Zone 2 rule: imports ONLY Python 3.11 stdlib.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform
import struct
import sys
from pathlib import Path

# Linux mount(2) flags
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_REMOUNT = 32
MS_REC = 1 << 14
MS_PRIVATE = 1 << 18

# Linux prctl(2) & seccomp constants
PR_SET_SECCOMP = 22
PR_SET_NO_NEW_PRIVS = 38
SECCOMP_MODE_FILTER = 2

BPF_LD = 0x00
BPF_W = 0x00
BPF_ABS = 0x20
BPF_JMP = 0x05
BPF_JEQ = 0x10
BPF_K = 0x00
BPF_RET = 0x06

SECCOMP_RET_ALLOW = 0x7FFF0000
SECCOMP_RET_ERRNO_EPERM = 0x00050001  # SECCOMP_RET_ERRNO | 1 (EPERM)

AUDIT_ARCH_X86_64 = 0xC000003E
AUDIT_ARCH_AARCH64 = 0xC00000B7

# Blocked syscalls per architecture:
# (socket, ptrace, pivot_root, mount, umount2, process_vm_readv, process_vm_writev)
_BLOCKED_SYSCALLS_X86_64 = (41, 101, 155, 165, 166, 310, 311)
_BLOCKED_SYSCALLS_AARCH64 = (198, 117, 41, 40, 39, 270, 271)


class _SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.c_char_p),
    ]


def _load_libc() -> ctypes.CDLL:
    libc_name = ctypes.util.find_library("c") or "libc.so.6"
    libc = ctypes.CDLL(libc_name, use_errno=True)
    libc.mount.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_ulong,
        ctypes.c_char_p,
    ]
    libc.mount.restype = ctypes.c_int
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    return libc


def _build_seccomp_bpf_program() -> bytes | None:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch_const = AUDIT_ARCH_X86_64
        blocked = _BLOCKED_SYSCALLS_X86_64
    elif machine in ("aarch64", "arm64"):
        arch_const = AUDIT_ARCH_AARCH64
        blocked = _BLOCKED_SYSCALLS_AARCH64
    else:
        return None

    insns: list[tuple[int, int, int, int]] = [
        # Verify seccomp_data.arch (offset 4); if foreign arch -> EPERM
        (BPF_LD | BPF_W | BPF_ABS, 0, 0, 4),
        (BPF_JMP | BPF_JEQ | BPF_K, 1, 0, arch_const),
        (BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO_EPERM),
        # Load seccomp_data.nr (offset 0)
        (BPF_LD | BPF_W | BPF_ABS, 0, 0, 0),
    ]
    total = len(blocked)
    for idx, nr in enumerate(blocked):
        jump_to_errno = total - idx
        insns.append((BPF_JMP | BPF_JEQ | BPF_K, jump_to_errno, 0, nr))
    insns.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW))
    insns.append((BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO_EPERM))
    return b"".join(struct.pack("HBBI", op, jt, jf, k) for op, jt, jf, k in insns)


def _apply_kernel_mounts_and_seccomp(
    mask_dirs: list[str],
    *,
    readonly_dirs: list[str] = (),
    enable_seccomp: bool = True,
) -> None:
    libc = _load_libc()

    rc = libc.mount(b"none", b"/", None, MS_REC | MS_PRIVATE, None)
    if rc != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"mount(MS_REC|MS_PRIVATE, /) failed: {os.strerror(err)}")

    flags_setup = MS_NOSUID | MS_NODEV | MS_NOEXEC
    flags_ro = MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC | MS_REMOUNT
    seen: set[str] = set()
    for raw_dir in (*mask_dirs, *readonly_dirs):
        p = Path(raw_dir)
        if not p.is_dir():
            continue
        resolved = str(p.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        target = os.fsencode(resolved)
        rc = libc.mount(b"tmpfs", target, b"tmpfs", flags_setup, b"size=65536,mode=0555")
        if rc != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"tmpfs mask mount failed on {resolved}: {os.strerror(err)}")
        libc.mount(b"tmpfs", target, b"tmpfs", flags_ro, b"size=65536,mode=0555,ro")

    rc_np = libc.prctl(PR_SET_NO_NEW_PRIVS, 1, None, 0, 0)
    if rc_np != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"prctl(PR_SET_NO_NEW_PRIVS) failed: {os.strerror(err)}")

    if enable_seccomp:
        bpf_bytes = _build_seccomp_bpf_program()
        if bpf_bytes is not None:
            insn_count = len(bpf_bytes) // 8
            prog = _SockFprog(insn_count, ctypes.c_char_p(bpf_bytes))
            rc_sc = libc.prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, ctypes.byref(prog), 0, 0)
            if rc_sc != 0:
                err = ctypes.get_errno()
                raise OSError(err, f"prctl(PR_SET_SECCOMP) failed: {os.strerror(err)}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mask_dirs: list[str] = []
    readonly_dirs: list[str] = []
    chdir_target: str | None = None
    readonly_chdir = False
    enable_seccomp = True

    idx = 0
    target_argv: list[str] = []
    while idx < len(args):
        tok = args[idx]
        if tok == "--":
            target_argv = args[idx + 1 :]
            break
        if tok == "--mask-dir":
            if idx + 1 >= len(args):
                raise SystemExit("ns_launcher: --mask-dir requires an argument")
            mask_dirs.append(args[idx + 1])
            idx += 2
            continue
        if tok == "--chdir":
            if idx + 1 >= len(args):
                raise SystemExit("ns_launcher: --chdir requires an argument")
            chdir_target = args[idx + 1]
            idx += 2
            continue
        if tok == "--readonly-chdir":
            readonly_chdir = True
            idx += 1
            continue
        if tok == "--no-seccomp":
            enable_seccomp = False
            idx += 1
            continue
        raise SystemExit(f"ns_launcher: unknown option {tok!r}")

    if not target_argv:
        raise SystemExit("ns_launcher: missing target argv after '--'")

    if readonly_chdir and chdir_target is not None:
        readonly_dirs.append(chdir_target)

    _apply_kernel_mounts_and_seccomp(
        mask_dirs,
        readonly_dirs=readonly_dirs,
        enable_seccomp=enable_seccomp,
    )
    if chdir_target is not None:
        os.chdir(chdir_target)
    os.execv(target_argv[0], target_argv)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
