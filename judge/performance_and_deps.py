#!/usr/bin/env python3
"""Performance Benchmarks, Offline Dependency Audit & Dataset Matrix Builder (Phases 14 & 16).

Generates the remaining required TZ §23.5 machine-readable artifacts in
``artifacts/reports/latest/``:
  - ``performance_report.json`` (measured ``env.step`` p50/p95/p99 latency,
    episode disk size, peak RSS memory, hardware/OS/Python profile)
  - ``dependency_report.json`` (stdlib-only core verification, optional extras
    inventory, pinned Docker base image, offline execution attestation)
  - ``generator_report.json``
  - ``invariants_report.json``
  - ``verifier_report_index.json``
  - ``episode_matrix.csv``
  - ``limitations_snapshot.md``
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import json
import os
import platform
import resource
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import canonical_json, sha256_hex
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from gen.core.clean_twin import CleanTwinSpec, generate_clean_twin, verify_clean_invariants
from harness.sandbox import detect_security_profile

REPORT_DIR = REPO_ROOT / "artifacts" / "reports" / "latest"

CORE_PACKAGES = (
    "core",
    "contracts",
    "invariants",
    "gen",
    "verifier",
    "nlp",
    "env",
    "scoring",
    "seal",
    "harness",
    "adapter",
    "arena",
    "metamorphic",
    "judge",
)

OPTIONAL_EXTRAS = (
    "pytest",
    "hypothesis",
    "jsonschema",
    "numpy",
    "sklearn",
    "gymnasium",
    "matplotlib",
)


def _measure_performance() -> dict[str, Any]:
    dev_root = REPO_ROOT / "episodes" / "dev"
    ep_dirs = [p for p in sorted(dev_root.iterdir()) if (p / "public").is_dir()]
    sample_ep = ep_dirs[0]

    env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL", max_steps=100))
    env.reset(sample_ep / "public", cursor_seed=42)
    r0 = env.step(
        {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": "init",
            "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 5}},
        }
    )
    first_inv = f"INV:{r0['result']['records'][0]['doc_id']}"

    latencies_ms: list[float] = []
    # Measure 180 indexed & paginated queries across fresh resets
    for batch in range(3):
        env.reset(sample_ep / "public", cursor_seed=100 + batch)
        for i in range(60):
            if i % 3 == 0:
                act = {"tool": "get_document", "args": {"id": first_inv}}
            elif i % 3 == 1:
                act = {"tool": "list_records", "args": {"table": "invoices", "page_size": 10}}
            else:
                act = {"tool": "calc", "args": {"expression": "125000 * 485 / 100"}}
            req = {"protocol_version": PROTOCOL_VERSION, "request_id": f"p-{batch}-{i}", "action": act}
            t0 = time.perf_counter_ns()
            env.step(req)
            latencies_ms.append((time.perf_counter_ns() - t0) / 1_000_000.0)

    latencies_ms.sort()
    n = len(latencies_ms)
    p50 = latencies_ms[int(n * 0.50)]
    p95 = latencies_ms[int(n * 0.95)]
    p99 = latencies_ms[min(n - 1, int(n * 0.99))]

    # Episode disk sizes across checked-in episodes
    ep_sizes: list[int] = []
    for split_dir in sorted((REPO_ROOT / "episodes").iterdir()):
        if not split_dir.is_dir():
            continue
        for ep in sorted(split_dir.iterdir()):
            if ep.is_dir():
                sz = sum(f.stat().st_size for f in ep.rglob("*") if f.is_file())
                ep_sizes.append(sz)
    max_ep_bytes = max(ep_sizes) if ep_sizes else 0
    max_ep_mb = max_ep_bytes / (1024.0 * 1024.0)

    # Peak RSS (on Linux ru_maxrss is KiB; on macOS bytes)
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mb = (raw_rss / 1024.0) if sys.platform.startswith("linux") else (raw_rss / (1024.0 * 1024.0))

    targets_ok = (p99 < 5.0) and (max_ep_mb < 50.0) and (peak_rss_mb < 300.0)
    return {
        "schema_version": "1.0.0",
        "report_type": "performance_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex({"p99_ms_limit": "5.0", "max_ep_mb_limit": "50.0", "peak_rss_mb_limit": "300.0"}),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "cpu_count_logical": os.cpu_count() or 1,
        "python_version": sys.version.split()[0],
        "command": "python3 judge/performance_and_deps.py",
        "status": "PASS" if targets_ok else "FAIL",
        "metrics": {
            "env_step_samples": n,
            "env_step_p50_ms": round(p50, 4),
            "env_step_p95_ms": round(p95, 4),
            "env_step_p99_ms": round(p99, 4),
            "target_env_step_p99_ms_lt": 5.0,
            "max_episode_disk_bytes": max_ep_bytes,
            "max_episode_disk_mb": round(max_ep_mb, 4),
            "target_episode_disk_mb_lt": 50.0,
            "peak_rss_mb": round(peak_rss_mb, 2),
            "target_peak_rss_mb_lt": 300.0,
        },
        "caveat": "Measured on the host recorded in 'platform'; judge hardware timings may vary slightly.",
    }


def _audit_dependencies() -> dict[str, Any]:
    stdlib_names = set(sys.stdlib_module_names)
    local_roots = set(CORE_PACKAGES) | {"tools", "tests", "judge_adapter"}
    third_party_imports: list[str] = []

    for pkg in CORE_PACKAGES:
        pkg_dir = REPO_ROOT / pkg
        if not pkg_dir.is_dir():
            continue
        for py in sorted(pkg_dir.rglob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    if m not in stdlib_names and m not in local_roots:
                        third_party_imports.append(f"{py.relative_to(REPO_ROOT)}:{m}")

    dockerfile_txt = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8") if (REPO_ROOT / "Dockerfile").is_file() else ""
    pinned_py311 = "FROM python:3.11" in dockerfile_txt
    pinned_digest = "@sha256:" in dockerfile_txt
    non_root_user = "USER 10001" in dockerfile_txt
    extras_state = {
        ext: ("PRESENT" if importlib.util.find_spec(ext) is not None else "ABSENT_OPTIONAL")
        for ext in OPTIONAL_EXTRAS
    }
    sec_prof = detect_security_profile()
    clean_core = len(third_party_imports) == 0 and pinned_py311 and non_root_user

    return {
        "schema_version": "1.0.0",
        "report_type": "dependency_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex({"core_packages": list(CORE_PACKAGES)}),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 judge/performance_and_deps.py",
        "status": "PASS" if clean_core else "FAIL",
        "core_stdlib_only": len(third_party_imports) == 0,
        "unexpected_third_party_imports_in_core": third_party_imports,
        "dockerfile_python_311_pinned": pinned_py311,
        "dockerfile_non_root_user_pinned": non_root_user,
        "dockerfile_base_image_digest_pinned": pinned_digest,
        "runtime_network_required": False,
        "active_security_profile": sec_prof.to_dict(),
        "optional_extras": extras_state,
    }


def _build_dataset_and_verifier_artifacts() -> None:
    episodes_root = REPO_ROOT / "episodes"
    matrix_rows: list[dict[str, Any]] = []
    verifier_index: list[dict[str, Any]] = []

    for split_dir in sorted(episodes_root.iterdir()):
        if not split_dir.is_dir():
            continue
        split_name = split_dir.name
        for ep in sorted(split_dir.iterdir()):
            man_path = ep / "manifest.json"
            if not man_path.is_file():
                continue
            man = json.loads(man_path.read_text(encoding="utf-8"))
            prof = man.get("profile", {})
            v_path = ep / "verifier_report.json"
            v_findings = 0
            v_digest = ""
            if v_path.is_file():
                v_raw = v_path.read_bytes()
                v_obj = json.loads(v_raw.decode("utf-8"))
                v_findings = len(v_obj.get("findings", []))
                import hashlib

                v_digest = hashlib.sha256(v_raw.rstrip(b"\n")).hexdigest()
                verifier_index.append(
                    {
                        "split": split_name,
                        "episode_id": man.get("episode_id", ep.name),
                        "verifier_version": v_obj.get("verifier_version", ""),
                        "findings_count": v_findings,
                        "report_sha256": v_digest,
                        "path": str(v_path.relative_to(REPO_ROOT)),
                    }
                )
            matrix_rows.append(
                {
                    "split": split_name,
                    "episode_id": man.get("episode_id", ep.name),
                    "difficulty": prof.get("difficulty_tier", prof.get("company_size", "M")),
                    "functional_currency": prof.get("functional_currency", "KZT"),
                    "id_style": prof.get("id_style", "A"),
                    "distractor_count": prof.get("distractor_count", 0),
                    "verifier_findings": v_findings,
                    "truth_commitment_prefix": str(man.get("truth_commitment", ""))[:16],
                }
            )

    # Write episode_matrix.csv
    csv_path = REPORT_DIR / "episode_matrix.csv"
    fieldnames = [
        "split",
        "episode_id",
        "difficulty",
        "functional_currency",
        "id_style",
        "distractor_count",
        "verifier_findings",
        "truth_commitment_prefix",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matrix_rows)

    # Write generator_report.json
    clean_twin = generate_clean_twin(CleanTwinSpec(episode_id="ep_gen_probe", master_seed=2025, enable_text_layer=True))
    inv_errs = verify_clean_invariants(clean_twin)
    meta_hdr = {
        "schema_version": "1.0.0",
        "code_version": "twinledger@1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": "python3 judge/performance_and_deps.py",
    }
    gen_rep = {
        **meta_hdr,
        "report_type": "generator_report",
        "config_hash": sha256_hex({"episodes_indexed": len(matrix_rows)}),
        "status": "PASS" if not inv_errs and len(matrix_rows) > 0 else "FAIL",
        "episodes_total": len(matrix_rows),
        "splits": sorted({r["split"] for r in matrix_rows}),
        "multilingual_profiles_supported": ["en", "ru", "kk", "mixed"],
        "anomaly_classes_supported": [
            "DUPLICATE_PAYMENT",
            "PARTIAL_PAYMENT_ALLOCATION",
            "FX_RATE_MISMATCH",
            "PERIOD_CUTOFF",
        ],
    }
    (REPORT_DIR / "generator_report.json").write_text(canonical_json(gen_rep) + "\n", encoding="utf-8")

    # Write invariants_report.json
    inv_rep = {
        **meta_hdr,
        "report_type": "invariants_report",
        "config_hash": sha256_hex({"invariants": [f"INV-{i:02d}" for i in range(1, 16)]}),
        "status": "PASS" if len(inv_errs) == 0 else "FAIL",
        "invariants_catalog_count": 15,
        "clean_twin_probe_violations": inv_errs,
    }
    (REPORT_DIR / "invariants_report.json").write_text(canonical_json(inv_rep) + "\n", encoding="utf-8")

    # Write verifier_report_index.json
    ver_idx_rep = {
        **meta_hdr,
        "report_type": "verifier_report_index",
        "config_hash": sha256_hex({"count": len(verifier_index)}),
        "status": "PASS" if len(verifier_index) > 0 else "FAIL",
        "verified_episodes_count": len(verifier_index),
        "episodes": verifier_index,
    }
    (REPORT_DIR / "verifier_report_index.json").write_text(canonical_json(ver_idx_rep) + "\n", encoding="utf-8")

    # Snapshot docs/LIMITATIONS.md -> limitations_snapshot.md
    lim_src = REPO_ROOT / "docs" / "LIMITATIONS.md"
    lim_dst = REPORT_DIR / "limitations_snapshot.md"
    if lim_src.is_file():
        shutil.copyfile(lim_src, lim_dst)
    else:
        lim_dst.write_text("# TwinLedger Known Limitations Snapshot\nSee docs/LIMITATIONS.md.\n", encoding="utf-8")


def run_all_aux_reports() -> tuple[dict[str, Any], dict[str, Any]]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    perf = _measure_performance()
    deps = _audit_dependencies()
    (REPORT_DIR / "performance_report.json").write_text(canonical_json(perf) + "\n", encoding="utf-8")
    (REPORT_DIR / "dependency_report.json").write_text(canonical_json(deps) + "\n", encoding="utf-8")
    _build_dataset_and_verifier_artifacts()
    return perf, deps


def main() -> int:
    perf, deps = run_all_aux_reports()
    ok = perf["status"] == "PASS" and deps["status"] == "PASS"
    print(
        f"[{'PASS' if ok else 'FAIL'}] perf & deps: step_p99={perf['metrics']['env_step_p99_ms']}ms, "
        f"peak_rss={perf['metrics']['peak_rss_mb']}MB, stdlib_only={deps['core_stdlib_only']} -> {REPORT_DIR}"
    )
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
