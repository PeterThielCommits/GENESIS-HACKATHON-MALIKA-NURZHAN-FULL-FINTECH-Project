"""Loader row-order & bounded-read regression tests (review remediation D-10-03).

Two defects fixed and locked here:

1. **Row order** — README "Canonical Tables": *file row order is preserved
   verbatim on load* (paired permutation checks ``P01..P05``, ``P11..P20``).
   ``env/loader.py::load_public_book`` used to re-sort rows by primary key;
   both episode loaders must now expose rows exactly as stored and
   ``list_records`` pagination must page over file order.

2. **Bounded reads** — every episode-supplied file read (``env/loader.py``,
   ``adapter/official_env.py``, ``scoring/official_scorer.py``,
   ``verifier/public_loader.py``) is capped in bytes and rows
   (``contracts.loader.MAX_INPUT_FILE_BYTES`` / ``MAX_INPUT_ROWS``), so an
   oversized or hostile file fails fast with a fixed ``LIMIT``-class error
   instead of exhausting memory or stalling startup.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapter.official_env import load_official_public_book
from contracts.loader import read_text_bounded
from env.environment import TwinLedgerEnv
from env.errors import EnvError
from env.loader import load_public_book
from scoring.official_scorer import collect_accessible_ids_from_episode_dir
from verifier.public_loader import PublicEpisodeError, load_public_episode

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_EP = REPO_ROOT / "episodes" / "dev" / "ep_dev_006_compound_all4"


def _req(req_id: str, tool: str, args: dict) -> dict:
    return {
        "protocol_version": "1.0",
        "request_id": req_id,
        "action": {"tool": tool, "args": args},
    }


def _copy_episode_with_reversed_invoices(td: Path) -> tuple[Path, list[dict]]:
    """Copy SAMPLE_EP/public and rewrite invoices.jsonl in reverse row order."""
    pub = td / "public"
    shutil.copytree(SAMPLE_EP / "public", pub)
    inv_path = pub / "invoices.jsonl"
    rows = [json.loads(ln) for ln in inv_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) > 2, "sample episode must have >2 invoices"
    rows.reverse()
    inv_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return pub, rows


class TestLoaderRowOrderPreserved(unittest.TestCase):
    """Defect 1: both loaders must preserve file row order verbatim."""

    def test_env_loader_preserves_file_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, rows = _copy_episode_with_reversed_invoices(Path(td))
            book = load_public_book(pub)
            self.assertEqual([dict(r) for r in book.tables["invoices"]], rows)

    def test_adapter_loader_preserves_file_row_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, rows = _copy_episode_with_reversed_invoices(Path(td))
            book = load_official_public_book(pub)
            self.assertEqual([dict(r) for r in book.tables["invoices"]], rows)

    def test_list_records_pagination_pages_follow_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, rows = _copy_episode_with_reversed_invoices(Path(td))
            env = TwinLedgerEnv()
            env.reset(pub)
            seen: list[str] = []
            cursor = None
            for page_no in range(1, 50):
                args: dict = {"table": "invoices", "page_size": 5}
                if cursor is not None:
                    args["cursor"] = cursor
                resp = env.step(_req(f"p-{page_no}", "list_records", args))
                self.assertTrue(resp["ok"], msg=str(resp))
                seen.extend(str(r["doc_id"]) for r in resp["result"]["records"])
                cursor = resp["result"]["next_cursor"]
                if cursor is None:
                    break
            self.assertEqual(seen, [str(r["doc_id"]) for r in rows])

    def test_generated_episode_order_matches_file_order_regression(self) -> None:
        # Guard: generator writes pk-sorted files, so preserved order must
        # equal the previous sorted behaviour on real generated episodes.
        book = load_public_book(SAMPLE_EP / "public")
        for table, pk in (
            ("invoices", "doc_id"),
            ("journal_entries", "je_id"),
            ("payments", "pay_id"),
        ):
            ids = [str(r.get(pk, "")) for r in book.tables[table]]
            self.assertEqual(ids, sorted(ids), msg=f"{table} sample should be pk-sorted on disk")


class TestBoundedEpisodeReads(unittest.TestCase):
    """Defect 2: episode-supplied reads are byte- and row-capped everywhere."""

    def test_read_text_bounded_exact_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "f.txt"
            p.write_bytes(b"x" * 10)
            self.assertEqual(read_text_bounded(p, max_bytes=10), "x" * 10)
            with self.assertRaises(ValueError):
                read_text_bounded(p, max_bytes=9)
            p.write_bytes(b"\xff\xfe not utf8")
            with self.assertRaises(ValueError):
                read_text_bounded(p, max_bytes=1024)

    def test_env_loader_rejects_oversized_file_with_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            with mock.patch("contracts.loader.MAX_INPUT_FILE_BYTES", 256):
                with self.assertRaises(EnvError) as cm:
                    load_public_book(pub)
            self.assertEqual(cm.exception.code, "LIMIT")

    def test_env_loader_rejects_too_many_rows_with_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            with mock.patch("contracts.loader.MAX_INPUT_ROWS", 2):
                with self.assertRaises(EnvError) as cm:
                    load_public_book(pub)
            self.assertEqual(cm.exception.code, "LIMIT")

    def test_adapter_rejects_oversized_file_and_row_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            with mock.patch("contracts.loader.MAX_INPUT_FILE_BYTES", 256):
                with self.assertRaises(EnvError) as cm:
                    load_official_public_book(pub)
            self.assertEqual(cm.exception.code, "LIMIT")
            with mock.patch("contracts.loader.MAX_INPUT_ROWS", 2):
                with self.assertRaises(EnvError) as cm:
                    load_official_public_book(pub)
            self.assertEqual(cm.exception.code, "LIMIT")

    def test_adapter_documents_subfolder_reads_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            docs = pub / "documents"
            docs.mkdir()
            (docs / "big.txt").write_text("A" * 4096, encoding="utf-8")
            with mock.patch("contracts.loader.MAX_INPUT_FILE_BYTES", 1024):
                with self.assertRaises(EnvError) as cm:
                    load_official_public_book(pub)
            self.assertEqual(cm.exception.code, "LIMIT")

    def test_scorer_and_verifier_reads_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            with mock.patch("contracts.loader.MAX_INPUT_FILE_BYTES", 256):
                with self.assertRaises(ValueError):
                    collect_accessible_ids_from_episode_dir(pub)
                with self.assertRaises(PublicEpisodeError):
                    load_public_episode(pub)

    def test_verifier_rejects_row_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pub, _ = _copy_episode_with_reversed_invoices(Path(td))
            with mock.patch("contracts.loader.MAX_INPUT_ROWS", 2):
                with self.assertRaises(PublicEpisodeError):
                    load_public_episode(pub)


if __name__ == "__main__":
    unittest.main()
