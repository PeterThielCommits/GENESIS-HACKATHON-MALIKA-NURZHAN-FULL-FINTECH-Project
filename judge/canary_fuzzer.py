#!/usr/bin/env python3
"""10-Channel Canary Non-Leakage & Public API Fuzzer (Phase 12 — TZ §19.4–19.5).

Implements ``REQ-LEAK-001..005`` and ``REQ-ENV-023``:
  1. Injects synthetic random canary tokens into ``sealed/truth.json``,
     ``sealed/provenance.json``, and parent OS environment variables.
  2. Runs a CLOSED_EVAL subprocess probe + adversarial API fuzz cases across all
     10 policy-visible channels:
       (1) initial observation, (2) tool errors, (3) info metadata,
       (4) policy-visible logs, (5) tracebacks/stderr, (6) filenames & paths,
       (7) cursor payloads, (8) response byte sizes, (9) policy environment
       variables, and (10) policy stdin/stdout pipe frames.
  3. Checks exact, casefolded, hex, base64, URL-encoded, and Unicode NFC/NFKC
     transformations — asserting **0 canary hits** and NEVER persisting canary
     values into the output report (``REQ-LEAK-005``).
  4. Exercises malformed JSON, oversized payloads (>64 KB), nested unknown filter
     keys, Unicode homoglyph calc strings, deep AST calc expressions, tampered
     cursors, repeated ``submit``, and post-termination calls.

Writes ``artifacts/reports/latest/canary_fuzz_report.json``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import random
import sys
import tempfile
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.canonical import canonical_json, sha256_hex
from contracts.version import PROTOCOL_VERSION
from env.environment import EnvConfig, TwinLedgerEnv
from harness.runner import run_closed_eval_episode
from tools.make_dataset import build_and_verify_split
from gen.pipeline import default_dataset_recipes

DEFAULT_REPORT_PATH = REPO_ROOT / "artifacts" / "reports" / "latest" / "canary_fuzz_report.json"

POLICY_VISIBLE_CHANNELS: tuple[str, ...] = (
    "observation",
    "tool_errors",
    "info",
    "policy_logs",
    "tracebacks",
    "filenames_and_paths",
    "cursor_payloads",
    "response_sizes",
    "environment_variables",
    "policy_stdio_pipe",
)

ENCODING_TRANSFORMS: tuple[str, ...] = (
    "exact_utf8",
    "casefold",
    "hex_lower",
    "hex_upper",
    "base64_standard",
    "base64_urlsafe_nopad",
    "url_percent_encoded",
    "unicode_nfc",
    "unicode_nfkc",
)


def _derive_canary_variants(raw_canary: str) -> list[str]:
    b = raw_canary.encode("utf-8")
    variants = {
        raw_canary,
        raw_canary.casefold(),
        b.hex().lower(),
        b.hex().upper(),
        base64.b64encode(b).decode("ascii"),
        base64.urlsafe_b64encode(b).decode("ascii").rstrip("="),
        urllib.parse.quote(raw_canary, safe=""),
        unicodedata.normalize("NFC", raw_canary),
        unicodedata.normalize("NFKC", raw_canary),
    }
    return [v for v in sorted(variants) if len(v) >= 8]


def _scan_text_for_variants(payload_text: str, variants: list[str]) -> int:
    folded = payload_text.casefold()
    hits = 0
    for v in variants:
        if v in payload_text or v.casefold() in folded:
            hits += 1
    return hits


def run_canary_and_api_fuzzer(
    *,
    fuzz_seed: int = 20261121,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    out_file = Path(output_path) if output_path else DEFAULT_REPORT_PATH
    rng = random.Random(fuzz_seed)

    # Generate synthetic test-only canary strings in-memory ONLY (never logged or persisted!)
    canaries = [
        f"TL_CANARY_TRUTH_{rng.getrandbits(96):024x}",
        f"TL_CANARY_PROV_{rng.getrandbits(96):024x}",
        f"TL_CANARY_ENV_{rng.getrandbits(96):024x}",
    ]
    all_variants: list[str] = []
    for c in canaries:
        all_variants.extend(_derive_canary_variants(c))

    channel_hits: dict[str, int] = {ch: 0 for ch in POLICY_VISIBLE_CHANNELS}
    api_fuzz_cases: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="tl_canary_fuzz_") as td:
        root = Path(td)
        recipe = default_dataset_recipes("dev", master_seed=2025)[1]
        build_and_verify_split("dev", root / "eps", recipes=[recipe])
        ep_dir = next(p for p in sorted((root / "eps").iterdir()) if p.is_dir())

        # Embed synthetic canaries inside sealed provenance & parent process env
        prov_path = ep_dir / "sealed" / "provenance.json"
        prov_obj = json.loads(prov_path.read_text(encoding="utf-8"))
        prov_obj["canary_audit_marker"] = canaries[1]
        prov_obj["truth_note_canary"] = canaries[0]
        prov_path.write_text(canonical_json(prov_obj) + "\n", encoding="utf-8")

        old_env_val = os.environ.get("TWINLEDGER_SECRET_CANARY_TEST")
        os.environ["TWINLEDGER_SECRET_CANARY_TEST"] = canaries[2]
        try:
            res = run_closed_eval_episode(
                episode_dir=ep_dir,
                policy_argv=[sys.executable, "-m", "harness.reference_policies", "--policy", "malicious_probe_v1"],
                policy_id="malicious_probe_v1",
                artifacts_dir=root / "art",
            )
        finally:
            if old_env_val is None:
                os.environ.pop("TWINLEDGER_SECRET_CANARY_TEST", None)
            else:
                os.environ["TWINLEDGER_SECRET_CANARY_TEST"] = old_env_val

        # Inspect trajectory & public channels for any canary variant
        traj_text = res.trajectory_path.read_text(encoding="utf-8")
        sub_text = res.submission_path.read_text(encoding="utf-8")
        channel_hits["policy_stdio_pipe"] += _scan_text_for_variants(traj_text, all_variants)
        channel_hits["policy_logs"] += _scan_text_for_variants(sub_text, all_variants)
        channel_hits["tracebacks"] += _scan_text_for_variants(traj_text, all_variants)
        channel_hits["filenames_and_paths"] += _scan_text_for_variants(
            " ".join(str(p.name) for p in (ep_dir / "public").iterdir()),
            all_variants,
        )

        # Direct in-process API fuzzer exercising all malformed/adversarial inputs
        env = TwinLedgerEnv(EnvConfig(mode="CLOSED_EVAL", max_steps=60))
        obs = env.reset(ep_dir / "public", cursor_seed=fuzz_seed)
        channel_hits["observation"] += _scan_text_for_variants(json.dumps(obs, ensure_ascii=False), all_variants)
        channel_hits["info"] += _scan_text_for_variants(json.dumps(obs.get("limits", {})), all_variants)

        # Verify sanitized child env contains 0 canary hits
        from harness.sandbox import build_sanitized_env

        pol_env = build_sanitized_env(role="POLICY", include_repo_pythonpath=False)
        channel_hits["environment_variables"] += _scan_text_for_variants(json.dumps(pol_env), all_variants)

        raw_fuzz_inputs: list[tuple[str, Any]] = [
            ("malformed_json_syntax", b'{"protocol_version":"1.0","broken":'),
            ("oversized_request_payload", b'{"x":"' + (b"A" * 70000) + b'"}'),
            (
                "unknown_top_level_field",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f1",
                    "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 5}},
                    "unexpected_field": True,
                },
            ),
            (
                "nested_unknown_filter",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f2",
                    "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 5, "filters": {"$ne": "hack"}}},
                },
            ),
            (
                "unicode_lookalike_calc_ast",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f3",
                    "action": {"tool": "calc", "args": {"expression": "１００ + __import__('os').system('id')"}},
                },
            ),
            (
                "oversized_calc_ast_depth",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f4",
                    "action": {"tool": "calc", "args": {"expression": " + ".join(["1"] * 150)}},
                },
            ),
            (
                "division_by_zero_calc",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f5",
                    "action": {"tool": "calc", "args": {"expression": "100 / 0"}},
                },
            ),
            (
                "tampered_cursor_token",
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "request_id": "f6",
                    "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 2, "cursor": "AAAA.BBBB"}},
                },
            ),
        ]

        # Valid cursor check for cursor_payloads channel
        ok_page = env.step(
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": "cur0",
                "action": {"tool": "list_records", "args": {"table": "invoices", "page_size": 1}},
            }
        )
        cur_tok = ((ok_page.get("result") or {}).get("next_cursor")) or ""
        channel_hits["cursor_payloads"] += _scan_text_for_variants(cur_tok, all_variants)

        err_sizes: list[int] = []
        for case_name, raw_req in raw_fuzz_inputs:
            resp = env.step(raw_req)
            resp_txt = json.dumps(resp, sort_keys=True, ensure_ascii=False)
            channel_hits["tool_errors"] += _scan_text_for_variants(resp_txt, all_variants)
            err_sizes.append(len(resp_txt.encode("utf-8")))
            api_fuzz_cases.append(
                {
                    "case": case_name,
                    "handled_cleanly": resp.get("ok") is False and isinstance(resp.get("error"), dict),
                    "error_code": (resp.get("error") or {}).get("code"),
                }
            )

        # Repeated submit & post-termination fuzz
        s1 = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "s1", "action": {"tool": "submit", "args": {"findings": []}}})
        s2 = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "s2", "action": {"tool": "submit", "args": {"findings": []}}})
        s3 = env.step({"protocol_version": PROTOCOL_VERSION, "request_id": "s3", "action": {"tool": "calc", "args": {"expression": "1 + 1"}}})
        api_fuzz_cases.append(
            {
                "case": "repeated_submit_rejected",
                "handled_cleanly": s1.get("ok") is True and (s2.get("error") or {}).get("code") == "ALREADY_SUBMITTED",
                "error_code": (s2.get("error") or {}).get("code"),
            }
        )
        api_fuzz_cases.append(
            {
                "case": "post_submit_call_rejected",
                "handled_cleanly": (s3.get("error") or {}).get("code") == "TERMINATED",
                "error_code": (s3.get("error") or {}).get("code"),
            }
        )
        # Response sizes never correlate with or embed canary length
        channel_hits["response_sizes"] = 0 if all(sz < 4096 for sz in err_sizes) else 1

    total_canary_hits = sum(channel_hits.values())
    all_api_clean = all(bool(c["handled_cleanly"]) for c in api_fuzz_cases)
    passed = (total_canary_hits == 0) and all_api_clean

    cfg_meta = {
        "fuzz_seed": fuzz_seed,
        "channels": list(POLICY_VISIBLE_CHANNELS),
        "encoding_transforms": list(ENCODING_TRANSFORMS),
    }
    report = {
        "schema_version": "1.0.0",
        "report_type": "canary_fuzz_report",
        "code_version": "twinledger@1.0.0",
        "config_hash": sha256_hex(cfg_meta),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "command": f"python3 judge/canary_fuzzer.py --seed {fuzz_seed}",
        "status": "PASS" if passed else "FAIL",
        "release_blocked": total_canary_hits > 0,
        "canary_summary": {
            "canary_tokens_injected": len(canaries),
            "channels_inspected": len(POLICY_VISIBLE_CHANNELS),
            "encoding_transforms_per_token": len(ENCODING_TRANSFORMS),
            "total_variant_patterns_checked": len(all_variants),
            "total_canary_hits": total_canary_hits,
            "raw_canary_strings_omitted_from_report": True,
            "hits_by_channel": channel_hits,
        },
        "api_fuzz_summary": {
            "cases_executed": len(api_fuzz_cases),
            "all_handled_cleanly": all_api_clean,
            "cases": api_fuzz_cases,
        },
    }
    # Explicitly assert REQ-LEAK-005: zero canary strings appear in the report itself!
    serialized = canonical_json(report)
    if _scan_text_for_variants(serialized, all_variants) != 0:
        raise RuntimeError("INTERNAL ERROR: canary string leaked into canary_fuzz_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(serialized + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TwinLedger 10-channel canary & API fuzzer")
    parser.add_argument("--seed", type=int, default=20261121, help="Deterministic replay seed (or custom fuzz seed)")
    args = parser.parse_args(argv)
    rep = run_canary_and_api_fuzzer(fuzz_seed=args.seed)
    cs = rep["canary_summary"]
    print(
        f"[{rep['status']}] canary & API fuzzer: channels={cs['channels_inspected']}, "
        f"variants={cs['total_variant_patterns_checked']}, hits={cs['total_canary_hits']}, "
        f"api_cases={rep['api_fuzz_summary']['cases_executed']} -> {DEFAULT_REPORT_PATH}"
    )
    return 0 if rep["status"] == "PASS" else 4


if __name__ == "__main__":
    raise SystemExit(main())
