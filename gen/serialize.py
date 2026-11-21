"""Deterministic episode serializer & manifest verifier (Phase 3 + Phase 4).

Writes an episode directory with strict public/sealed separation:
  - ``<ep_dir>/public/``: ONLY the 12 allowlisted public files (canonical JSON/JSONL)
  - ``<ep_dir>/manifest.json``: validates against frozen ``episode_manifest.schema.json``
  - ``<ep_dir>/sealed/truth.json``: list of frozen-schema-valid truth findings
  - ``<ep_dir>/sealed/provenance.json``: seed, operator outcomes, structural diff, salt

Never imports ``verifier``, ``scoring``, or ``seal``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from contracts.canonical import canonical_bytes
from contracts.loader import validate_instance
from gen.core.clean_twin import CleanTwin
from gen.truth import compute_truth_commitment, validate_truth_list

GENERATOR_VERSION = "twinledger-gen@1.0.0"

PUBLIC_JSON_FILES = (
    "company.json",
    "policy.json",
    "accounts.json",
    "opening_balances.json",
    "period_calendar.json",
)

PUBLIC_JSONL_FILES = (
    "counterparties.jsonl",
    "fx_rates.jsonl",
    "invoices.jsonl",
    "payments.jsonl",
    "credit_notes.jsonl",
    "bank_lines.jsonl",
    "journal_entries.jsonl",
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_canonical(path: Path, obj: Any) -> str:
    data = canonical_bytes(obj) + b"\n"
    path.write_bytes(data)
    return _sha256_bytes(data)


def _write_jsonl_canonical(path: Path, rows: Sequence[dict[str, Any]], sort_key: str) -> str:
    ordered = sorted(rows, key=lambda r: str(r.get(sort_key, "")))
    lines = [canonical_bytes(r) for r in ordered]
    data = (b"\n".join(lines) + b"\n") if lines else b""
    path.write_bytes(data)
    return _sha256_bytes(data)


_JSONL_SORT_KEYS: dict[str, str] = {
    "counterparties.jsonl": "counterparty_id",
    "fx_rates.jsonl": "fx_id",
    "invoices.jsonl": "doc_id",
    "payments.jsonl": "pay_id",
    "credit_notes.jsonl": "credit_note_id",
    "bank_lines.jsonl": "bank_line_id",
    "journal_entries.jsonl": "je_id",
}


def write_episode(
    episode_dir: Path | str,
    twin: CleanTwin,
    truths: Sequence[dict[str, Any]],
    *,
    config_hash: str,
    commitment_salt_hex: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Serialize an episode to disk and return the validated ``manifest.json`` dict."""
    t_errs = validate_truth_list(truths)
    if t_errs:
        raise ValueError(f"cannot write invalid truth findings: {t_errs}")

    ep_path = Path(episode_dir)
    pub_dir = ep_path / "public"
    sealed_dir = ep_path / "sealed"
    pub_dir.mkdir(parents=True, exist_ok=True)
    sealed_dir.mkdir(parents=True, exist_ok=True)

    tables = twin.public_tables()
    public_files: list[dict[str, str]] = []

    for fname in PUBLIC_JSON_FILES:
        digest = _write_json_canonical(pub_dir / fname, tables[fname])
        public_files.append({"path": f"public/{fname}", "sha256": digest})

    for fname in PUBLIC_JSONL_FILES:
        digest = _write_jsonl_canonical(pub_dir / fname, tables[fname], _JSONL_SORT_KEYS[fname])
        public_files.append({"path": f"public/{fname}", "sha256": digest})

    public_files.sort(key=lambda x: x["path"])

    truth_commitment = compute_truth_commitment(truths, commitment_salt_hex)
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "episode_id": twin.episode_id,
        "contract_version": "1.0.0",
        "generator_version": GENERATOR_VERSION,
        "config_hash": config_hash,
        "public_files": public_files,
        "truth_commitment": truth_commitment,
        "profile": {
            "record_count_by_table": {
                "accounts": len(twin.accounts),
                "counterparties": len(twin.counterparties),
                "fx_rates": len(twin.fx_rates),
                "invoices": len(twin.invoices),
                "payments": len(twin.payments),
                "credit_notes": len(twin.credit_notes),
                "bank_lines": len(twin.bank_lines),
                "journal_entries": len(twin.journal_entries),
            },
            "document_count": len(twin.invoices) + len(twin.credit_notes),
            "distractor_count": len(twin.distractor_log),
            "tool_budget": twin.policy["max_steps"],
        },
    }

    m_errs = validate_instance("episode_manifest", manifest)
    if m_errs:
        raise ValueError(f"generated manifest failed frozen schema: {m_errs}")

    _write_json_canonical(ep_path / "manifest.json", manifest)
    _write_json_canonical(sealed_dir / "truth.json", list(truths))
    _write_json_canonical(
        sealed_dir / "provenance.json",
        {
            "episode_id": twin.episode_id,
            "generator_version": GENERATOR_VERSION,
            "commitment_salt_hex": commitment_salt_hex,
            "truth_commitment": truth_commitment,
            "distractors": twin.distractor_log,
            **provenance,
        },
    )
    return manifest


def verify_episode_manifest(episode_dir: Path | str) -> list[str]:
    """Verify ``manifest.json`` schema and every public file's SHA-256 (REQ-DATA-021)."""
    ep_path = Path(episode_dir)
    manifest_path = ep_path / "manifest.json"
    if not manifest_path.is_file():
        return [f"missing manifest.json in {ep_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid manifest.json JSON: {exc}"]

    errors = validate_instance("episode_manifest", manifest)
    if errors:
        return errors

    expected_paths = {f"public/{f}" for f in PUBLIC_JSON_FILES + PUBLIC_JSONL_FILES}
    seen_paths: set[str] = set()
    for entry in manifest["public_files"]:
        rel = entry["path"]
        seen_paths.add(rel)
        target = ep_path / rel
        if not target.is_file():
            errors.append(f"missing public file: {rel}")
            continue
        actual = _sha256_bytes(target.read_bytes())
        if actual != entry["sha256"]:
            errors.append(f"sha256 mismatch for {rel}: expected {entry['sha256']}, got {actual}")

    missing_required = sorted(expected_paths - seen_paths)
    if missing_required:
        errors.append(f"manifest missing required public files: {missing_required}")

    # Check no extra files exist inside public/
    pub_dir = ep_path / "public"
    if pub_dir.is_dir():
        actual_files = {f"public/{p.name}" for p in pub_dir.iterdir()}
        extra = sorted(actual_files - seen_paths)
        if extra:
            errors.append(f"unlisted extra entries inside public/: {extra}")

    return errors


__all__ = [
    "GENERATOR_VERSION",
    "PUBLIC_JSONL_FILES",
    "PUBLIC_JSON_FILES",
    "verify_episode_manifest",
    "write_episode",
]
