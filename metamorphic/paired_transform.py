"""Deterministic paired transformations (Block 4: P01..P20).

Implements safe episode-copy transformations without touching the original:
  - ``permute_rows``: deterministic permutation of table rows while preserving
    intra-document semantic ordering (``line_items``, ``lines``).
  - ``remap_ids``: bijective, per-namespace ID remapping across all public
    tables, references, and sealed ``truth.json`` / ``provenance.json`` while
    preserving FX semantic fields (``effective_date``, ``pair``, ``rate_decimal``)
    and returning the exact inverse map for post-run verification.
"""

from __future__ import annotations

import copy
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PairedTransformResult:
    """Output of creating a transformed copy of an episode directory."""

    transformed_dir: Path
    forward_map: dict[str, str]  # original ID (raw & typed) -> remapped ID
    inverse_map: dict[str, str]  # remapped ID (raw & typed) -> original ID


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for r in rows]
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def _remap_typed(val: str, typed_map: dict[str, str], raw_map_by_prefix: dict[str, dict[str, str]]) -> str:
    if val in typed_map:
        return typed_map[val]
    if ":" in val:
        prefix, _, local = val.partition(":")
        if prefix in raw_map_by_prefix and local in raw_map_by_prefix[prefix]:
            return f"{prefix}:{raw_map_by_prefix[prefix][local]}"
    return val


def transform_episode_copy(
    src_episode_dir: Path | str,
    dst_episode_dir: Path | str,
    *,
    permute_rows: bool = False,
    remap_ids: bool = False,
    seed: int = 1337,
) -> PairedTransformResult:
    """Copy ``src_episode_dir`` to ``dst_episode_dir`` and apply safe transforms."""
    src = Path(src_episode_dir)
    dst = Path(dst_episode_dir)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    pub = dst / "public" if (dst / "public").is_dir() else dst
    rng = random.Random(seed)

    table_specs: list[tuple[str, str, str]] = [
        ("counterparties.jsonl", "counterparty_id", "CP"),
        ("fx_rates.jsonl", "fx_id", "FX"),
        ("invoices.jsonl", "doc_id", "INV"),
        ("payments.jsonl", "pay_id", "PAY"),
        ("credit_notes.jsonl", "credit_note_id", "CN"),
        ("bank_lines.jsonl", "bank_line_id", "BANK"),
        ("journal_entries.jsonl", "je_id", "JE"),
    ]

    loaded: dict[str, list[dict[str, Any]]] = {}
    for fname, _, _ in table_specs:
        p = pub / fname
        if p.is_file():
            loaded[fname] = _read_jsonl(p)

    forward_map: dict[str, str] = {}
    inverse_map: dict[str, str] = {}
    raw_map_by_prefix: dict[str, dict[str, str]] = {}

    if remap_ids:
        # Build independent bijective maps per namespace (no cross-table collisions)
        for fname, pk, prefix in table_specs:
            rows = loaded.get(fname, [])
            ns_map: dict[str, str] = {}
            counter = 1
            for row in rows:
                old_id = str(row[pk])
                if old_id in ns_map:
                    continue
                # Arbitrary neutral remapped ID format (explicitly testing non-prefix-dependent logic)
                token = f"RMP_{prefix}_{seed}_{counter:04d}"
                counter += 1
                ns_map[old_id] = token
                forward_map[old_id] = token
                inverse_map[token] = old_id
                forward_map[f"{prefix}:{old_id}"] = f"{prefix}:{token}"
                inverse_map[f"{prefix}:{token}"] = f"{prefix}:{old_id}"
            raw_map_by_prefix[prefix] = ns_map

        cp_map = raw_map_by_prefix.get("CP", {})
        inv_map = raw_map_by_prefix.get("INV", {})
        pay_map = raw_map_by_prefix.get("PAY", {})
        cn_map = raw_map_by_prefix.get("CN", {})
        bank_map = raw_map_by_prefix.get("BANK", {})
        fx_map = raw_map_by_prefix.get("FX", {})
        je_map = raw_map_by_prefix.get("JE", {})

        # Apply remapping consistently across all tables and cross-references
        for row in loaded.get("counterparties.jsonl", []):
            row["counterparty_id"] = cp_map.get(row["counterparty_id"], row["counterparty_id"])

        for row in loaded.get("fx_rates.jsonl", []):
            # Semantic fields (effective_date, pair, rate_decimal) remain untouched!
            row["fx_id"] = fx_map.get(row["fx_id"], row["fx_id"])

        for row in loaded.get("invoices.jsonl", []):
            row["doc_id"] = inv_map.get(row["doc_id"], row["doc_id"])
            if row.get("counterparty_id") in cp_map:
                row["counterparty_id"] = cp_map[row["counterparty_id"]]

        for row in loaded.get("payments.jsonl", []):
            row["pay_id"] = pay_map.get(row["pay_id"], row["pay_id"])
            if row.get("counterparty_id") in cp_map:
                row["counterparty_id"] = cp_map[row["counterparty_id"]]
            if row.get("bank_reference") in bank_map:
                row["bank_reference"] = bank_map[row["bank_reference"]]
            if row.get("related_payment_id") in pay_map:
                row["related_payment_id"] = pay_map[row["related_payment_id"]]
            for al in row.get("allocations", []):
                if al.get("document_id") in inv_map:
                    al["document_id"] = inv_map[al["document_id"]]

        for row in loaded.get("credit_notes.jsonl", []):
            row["credit_note_id"] = cn_map.get(row["credit_note_id"], row["credit_note_id"])
            if row.get("invoice_id") in inv_map:
                row["invoice_id"] = inv_map[row["invoice_id"]]
            if row.get("counterparty_id") in cp_map:
                row["counterparty_id"] = cp_map[row["counterparty_id"]]

        for row in loaded.get("bank_lines.jsonl", []):
            row["bank_line_id"] = bank_map.get(row["bank_line_id"], row["bank_line_id"])

        for row in loaded.get("journal_entries.jsonl", []):
            row["je_id"] = je_map.get(row["je_id"], row["je_id"])
            src_doc = row.get("source_document_id")
            if isinstance(src_doc, str):
                if src_doc in inv_map:
                    row["source_document_id"] = inv_map[src_doc]
                elif src_doc in pay_map:
                    row["source_document_id"] = pay_map[src_doc]
                elif src_doc in cn_map:
                    row["source_document_id"] = cn_map[src_doc]
            for ln in row.get("lines", []):
                if ln.get("counterparty_id") in cp_map:
                    ln["counterparty_id"] = cp_map[ln["counterparty_id"]]

        # Consistently remap sealed truth.json (judge-side only)
        truth_path = dst / "sealed" / "truth.json"
        if truth_path.is_file():
            truths = json.loads(truth_path.read_text(encoding="utf-8"))
            for t in truths:
                t["affected_ids"] = [
                    _remap_typed(aid, forward_map, raw_map_by_prefix)
                    for aid in t.get("affected_ids", [])
                ]
                t["evidence_sets"] = [
                    [_remap_typed(eid, forward_map, raw_map_by_prefix) for eid in es]
                    for es in t.get("evidence_sets", [])
                ]
            truth_path.write_text(
                json.dumps(truths, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    if permute_rows:
        for fname, _, _ in table_specs:
            if fname in loaded and len(loaded[fname]) > 1:
                rows_copy = copy.deepcopy(loaded[fname])
                # Guarantee a non-trivial permutation when len >= 2
                original_order = list(rows_copy)
                rng.shuffle(rows_copy)
                if rows_copy == original_order:
                    rows_copy.append(rows_copy.pop(0))
                loaded[fname] = rows_copy

    for fname, rows in loaded.items():
        _write_jsonl(pub / fname, rows)

    return PairedTransformResult(
        transformed_dir=dst,
        forward_map=forward_map,
        inverse_map=inverse_map,
    )


def invert_findings_ids(
    findings_payload: dict[str, Any],
    inverse_map: dict[str, str],
) -> dict[str, Any]:
    """Map remapped IDs in findings back to original episode IDs for P06..P20 comparison."""
    out_list: list[dict[str, Any]] = []
    for item in findings_payload.get("findings", []):
        rec = copy.deepcopy(item)
        rec["affected_ids"] = sorted(inverse_map.get(x, x) for x in rec.get("affected_ids", []))
        rec["evidence_ids"] = sorted(inverse_map.get(x, x) for x in rec.get("evidence_ids", []))
        out_list.append(rec)
    out_list.sort(
        key=lambda x: (
            x.get("type", ""),
            tuple(x.get("affected_ids", [])),
            x.get("claimed_amount_minor", 0),
            x.get("currency", ""),
        )
    )
    return {"findings": out_list}


__all__ = [
    "PairedTransformResult",
    "invert_findings_ids",
    "transform_episode_copy",
]
