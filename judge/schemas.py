#!/usr/bin/env python3
"""Judge Kit artifact schemas (Phase 14 — Master TZ §23.4–23.5).

Stdlib-only validators for the machine-readable Judge Kit outputs. Each
``validate_*`` function returns a list of human-readable error strings;
an empty list means the artifact is valid. These validators deliberately
mirror ``contracts/rubric_check.schema.json`` and the TZ §23.3/§23.5 field
lists without requiring the optional ``jsonschema`` extra, so the core
verify path never depends on a third-party package (TZ §22.2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# NOTE: frozen judge/rubric_map.json (release_freeze.json) carries the version
# once at top level (`rubric_version`) and omits per-check `schema_version`,
# although contracts/rubric_check.schema.json requires it for a standalone
# check object. The map validator therefore requires the remaining fields and
# only checks `schema_version` when present (see D-14-02).
RUBRIC_CHECK_REQUIRED = (
    "check_id",
    "rubric_item",
    "req_id",
    "test_id",
    "command",
    "evidence_artifact",
    "provisional",
)

VERIFY_SUMMARY_REQUIRED = (
    "schema_version",
    "report_type",
    "status",
    "checks",
    "official_score_claimed",
)

VERIFY_CHECK_REQUIRED = (
    "check_id",
    "req_id",
    "rubric_item",
    "status",
    "reason",
    "required",
    "exit_code",
    "duration_s",
    "artifact",
)

REPORT_INDEX_REQUIRED = (
    "schema_version",
    "report_type",
    "offline_self_contained_html",
    "artifacts",
)


def validate_rubric_map(data: Any) -> list[str]:
    """Validate judge/rubric_map.json structure (TZ §23.4)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["rubric_map must be a JSON object"]
    if not isinstance(data.get("provisional"), bool):
        errors.append("rubric_map.provisional must be boolean")
    blocks = data.get("blocks")
    if isinstance(blocks, list) and blocks:
        total_weight = sum(
            b.get("provisional_weight", 0) for b in blocks if isinstance(b, dict)
        )
        if total_weight != 100:
            errors.append(f"rubric blocks provisional_weight must sum to 100, got {total_weight}")
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("rubric_map.checks must be a non-empty list")
        return errors
    seen: set[str] = set()
    for idx, check in enumerate(checks):
        where = f"checks[{idx}]"
        if not isinstance(check, dict):
            errors.append(f"{where} must be an object")
            continue
        for field in RUBRIC_CHECK_REQUIRED:
            if field not in check:
                errors.append(f"{where} missing required field '{field}'")
        if "schema_version" in check and check.get("schema_version") != "1.0.0":
            errors.append(f"{where}.schema_version must be '1.0.0'")
        if not isinstance(check.get("provisional"), bool):
            errors.append(f"{where}.provisional must be boolean")
        cid = check.get("check_id")
        if isinstance(cid, str):
            if cid in seen:
                errors.append(f"duplicate check_id '{cid}'")
            seen.add(cid)
    return errors


def validate_verify_summary(data: Any) -> list[str]:
    """Validate artifacts/reports/latest/verify_summary.json (TZ §23.3)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["verify_summary must be a JSON object"]
    for field in VERIFY_SUMMARY_REQUIRED:
        if field not in data:
            errors.append(f"verify_summary missing required field '{field}'")
    if data.get("report_type") != "verify_summary":
        errors.append("verify_summary.report_type must be 'verify_summary'")
    if data.get("status") not in ("PASS", "FAIL", "BLOCKED"):
        errors.append("verify_summary.status must be PASS/FAIL/BLOCKED")
    if data.get("official_score_claimed") is not False:
        errors.append("verify_summary.official_score_claimed must be false (TZ §23.6)")
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("verify_summary.checks must be a non-empty list")
        return errors
    for idx, check in enumerate(checks):
        where = f"checks[{idx}]"
        if not isinstance(check, dict):
            errors.append(f"{where} must be an object")
            continue
        for field in VERIFY_CHECK_REQUIRED:
            if field not in check:
                errors.append(f"{where} missing required field '{field}'")
        if check.get("status") not in ("PASS", "FAIL", "SKIPPED", "BLOCKED"):
            errors.append(f"{where}.status must be PASS/FAIL/SKIPPED/BLOCKED")
    return errors


def validate_report_index(data: Any) -> list[str]:
    """Validate artifacts/reports/latest/report_index.json (TZ §23.5)."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["report_index must be a JSON object"]
    for field in REPORT_INDEX_REQUIRED:
        if field not in data:
            errors.append(f"report_index missing required field '{field}'")
    if data.get("report_type") != "report_index":
        errors.append("report_index.report_type must be 'report_index'")
    if data.get("offline_self_contained_html") is not True:
        errors.append("report_index.offline_self_contained_html must be true")
    if not isinstance(data.get("artifacts"), list) or not data["artifacts"]:
        errors.append("report_index.artifacts must be a non-empty list")
    return errors


# TZ §23.5: "Каждый report должен содержать code version, config hash, run
# timestamp (для человеческой диагностики; исключён из deterministic hashes),
# target platform, Python version и команды запуска."
REPORT_ENVELOPE_REQUIRED = (
    "code_version",
    "config_hash",
    "generated_at_utc",
    "platform",
    "python_version",
    "command",
)


def validate_report_envelope(data: Any, name: str = "report") -> list[str]:
    """Validate the TZ §23.5 metadata envelope shared by every JSON report."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{name} must be a JSON object"]
    for field in REPORT_ENVELOPE_REQUIRED:
        value = data.get(field)
        if field not in data:
            errors.append(f"{name} missing envelope field '{field}'")
        elif not isinstance(value, str) or not value.strip():
            errors.append(f"{name}.{field} must be a non-empty string")
    cfg = data.get("config_hash")
    if isinstance(cfg, str) and cfg and not re.fullmatch(r"[0-9a-f]{64}", cfg):
        errors.append(f"{name}.config_hash must be a 64-char lowercase sha256 hex digest")
    ts = data.get("generated_at_utc")
    if isinstance(ts, str) and ts and not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts):
        errors.append(f"{name}.generated_at_utc must be ISO-8601 UTC with a trailing Z")
    return errors


def validate_report_dir_envelopes(report_dir: Path) -> list[str]:
    """Check the TZ §23.5 envelope on every JSON report in ``report_dir``.

    Unparseable files are reported (they must never be silently ignored in a
    release evidence directory). Non-``dict`` payloads are flagged too.
    """
    errors: list[str] = []
    for path in sorted(report_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: unparseable JSON: {exc}")
            continue
        errors.extend(validate_report_envelope(data, path.name))
    return errors
