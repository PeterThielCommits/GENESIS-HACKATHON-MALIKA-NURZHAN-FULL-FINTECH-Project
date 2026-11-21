"""Phase 5 environment, calculator, JSONL server, boundary, and adapter tests
(REQ-ARC-002, REQ-ARC-006, REQ-ENV-001..032).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from adapter.organizer import ADAPTER_PROVISIONAL, normalize_finding, normalize_tool_request
from contracts.loader import validate_instance
from contracts.models import Finding, TruthFinding
from env import EnvConfig, EnvError, TwinLedgerEnv, evaluate_calc, serve_stream
from scoring.reward import compute_reward

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_EP = REPO_ROOT / "episodes" / "dev" / "ep_dev_006_compound_all4"


def _req(req_id: str, tool: str, args: dict) -> dict:
    return {
        "protocol_version": "1.0",
        "request_id": req_id,
        "action": {"tool": tool, "args": args},
    }


class TestTwinLedgerEnvironment(unittest.TestCase):
    def test_reset_and_full_evidence_reachability_on_all_dev_episodes(self):
        dev_dirs = sorted(p for p in (REPO_ROOT / "episodes" / "dev").iterdir() if p.is_dir())
        self.assertGreaterEqual(len(dev_dirs), 6)
        for ep_dir in dev_dirs:
            env = TwinLedgerEnv()
            obs = env.reset(ep_dir / "public")
            self.assertEqual(obs["protocol_version"], "1.0")
            self.assertEqual(obs["mode"], "CLOSED_EVAL")

            # Every evidence ID emitted in verifier_report.json must be fetchable via env tools!
            rep = json.loads((ep_dir / "verifier_report.json").read_text(encoding="utf-8"))
            req_idx = 0
            for f in rep["findings"]:
                for ev_set in f["evidence_sets"]:
                    for eid in ev_set:
                        req_idx += 1
                        resp = env.step(_req(f"g-{req_idx}", "get_record", {"id": eid}))
                        self.assertEqual(validate_instance("tool_response", resp), [])
                        self.assertTrue(resp["ok"], msg=f"{ep_dir.name} failed get_record({eid}): {resp}")
                        self.assertEqual(resp["result"]["typed_id"], eid)

    def test_pagination_opaque_cursors_and_tamper_rejection(self):
        env = TwinLedgerEnv()
        env.reset(SAMPLE_EP / "public")

        seen: list[str] = []
        cursor = None
        pages = 0
        while True:
            pages += 1
            args = {"table": "journal_entries", "page_size": 5}
            if cursor is not None:
                args["cursor"] = cursor
            resp = env.step(_req(f"p-{pages}", "list_records", args))
            self.assertTrue(resp["ok"], msg=resp)
            seen.extend(r["je_id"] for r in resp["result"]["records"])
            cursor = resp["result"]["next_cursor"]
            if cursor is None:
                break
        self.assertGreater(pages, 2)
        self.assertEqual(len(seen), len(set(seen)))

        # Get valid cursor on page 1, then tamper / reuse on wrong table / wrong filter
        r1 = env.step(_req("c1", "list_records", {"table": "journal_entries", "page_size": 2}))
        valid_cursor = r1["result"]["next_cursor"]
        self.assertIsNotNone(valid_cursor)

        bad_tamper = env.step(_req("c2", "list_records", {"table": "journal_entries", "page_size": 2, "cursor": valid_cursor + "x"}))
        self.assertFalse(bad_tamper["ok"])
        self.assertEqual(bad_tamper["error"]["code"], "BAD_CURSOR")

        bad_table = env.step(_req("c3", "list_records", {"table": "invoices", "page_size": 2, "cursor": valid_cursor}))
        self.assertFalse(bad_table["ok"])
        self.assertEqual(bad_table["error"]["code"], "BAD_CURSOR")

        bad_filter = env.step(_req("c4", "list_records", {"table": "journal_entries", "filters": {"posting_period": "2025-04"}, "page_size": 2, "cursor": valid_cursor}))
        self.assertFalse(bad_filter["ok"])
        self.assertEqual(bad_filter["error"]["code"], "BAD_CURSOR")

    def test_filters_documents_and_bounded_errors(self):
        env = TwinLedgerEnv()
        env.reset(SAMPLE_EP / "public")

        # Valid filter
        r_ok = env.step(_req("f1", "list_records", {"table": "fx_rates", "filters": {"source_code": "NBK"}, "page_size": 5}))
        self.assertTrue(r_ok["ok"])
        self.assertTrue(all(x["source_code"] == "NBK" for x in r_ok["result"]["records"]))

        # Invalid filter key
        r_bf = env.step(_req("f2", "list_records", {"table": "fx_rates", "filters": {"secret_field": "1"}}))
        self.assertFalse(r_bf["ok"])
        self.assertEqual(r_bf["error"]["code"], "BAD_FILTER")

        # Document fetch (policy + invoice + missing)
        r_pol = env.step(_req("d1", "get_document", {"id": "policy"}))
        self.assertTrue(r_pol["ok"])
        self.assertEqual(r_pol["result"]["document"]["schema_version"], "1.0.0")

        r_miss = env.step(_req("d2", "get_document", {"id": "INV:NO_SUCH_DOC"}))
        self.assertFalse(r_miss["ok"])
        self.assertEqual(r_miss["error"]["code"], "NOT_FOUND")

        # Unknown tool
        r_unk = env.step(_req("u1", "read_secret", {}))
        self.assertFalse(r_unk["ok"])
        self.assertEqual(r_unk["error"]["code"], "UNKNOWN_TOOL")

    def test_safe_decimal_calculator_and_attack_rejection(self):
        self.assertEqual(evaluate_calc("100 * 483.125")["result"], "48312.5")
        self.assertEqual(evaluate_calc("round_half_even(100 * 483.125, 0)")["result"], "48312")
        self.assertEqual(evaluate_calc("round_half_up(100 * 483.125, 0)")["result"], "48313")
        self.assertEqual(evaluate_calc("abs(10 - 25) + max(1, 3, 2)")["result"], "18")

        malicious = [
            "__import__('os').system('echo pwn')",
            "(1).__class__.__bases__",
            "2 ** 1000000",
            "1 / 0",
            "[x for x in range(10)]",
            "lambda x: x",
            "True + 1",
            "1 + " * 120 + "1",
            "1" * 501,
        ]
        for expr in malicious:
            with self.assertRaises(EnvError) as ctx:
                evaluate_calc(expr)
            self.assertEqual(ctx.exception.code, "CALC_ERROR", msg=f"bad error for {expr!r}")

    def test_submit_closed_eval_budget_and_end_to_end_scoring(self):
        env = TwinLedgerEnv(EnvConfig(max_steps=5, submit_counts_as_step=False))
        env.reset(SAMPLE_EP / "public")

        # Submit invalid finding -> BAD_FINDING (does not terminate)
        r_bad = env.step(_req("s0", "submit", {"findings": [{"type": "UNKNOWN"}]}))
        self.assertFalse(r_bad["ok"])
        self.assertEqual(r_bad["error"]["code"], "BAD_FINDING")
        self.assertFalse(env.terminated)

        # Run 2 inspection steps, then submit findings matching verifier_report.json
        self.assertTrue(env.step(_req("q1", "calc", {"expression": "10 + 20"}))["ok"])
        self.assertTrue(env.step(_req("q2", "get_document", {"id": "company"}))["ok"])
        self.assertEqual(env.steps_used, 2)

        rep = json.loads((SAMPLE_EP / "verifier_report.json").read_text(encoding="utf-8"))
        submission = [
            {
                "schema_version": "1.0.0",
                "type": f["type"],
                "affected_ids": f["affected_ids"],
                "claimed_amount": f["claimed_amount_minor"],
                "currency": f["currency"],
                "evidence_ids": f["evidence_sets"][0],
            }
            for f in rep["findings"]
        ]
        r_sub = env.step(_req("s1", "submit", {"findings": submission}))
        self.assertTrue(r_sub["ok"], msg=r_sub)
        self.assertEqual(r_sub["result"]["mode"], "CLOSED_EVAL")
        self.assertIsNone(r_sub["result"]["reward"])
        self.assertEqual(r_sub["result"]["steps_used"], 2)  # submit_counts_as_step=False
        self.assertTrue(env.terminated)

        # Repeat submit -> ALREADY_SUBMITTED; further tool call -> TERMINATED
        r_dup = env.step(_req("s2", "submit", {"findings": []}))
        self.assertEqual(r_dup["error"]["code"], "ALREADY_SUBMITTED")
        r_after = env.step(_req("q3", "calc", {"expression": "1+1"}))
        self.assertEqual(r_after["error"]["code"], "TERMINATED")

        # Score the env submission externally via scoring.reward (if sealed truth present locally)
        truth_path = SAMPLE_EP / "sealed" / "truth.json"
        if truth_path.is_file():
            truths = [TruthFinding.from_dict(t) for t in json.loads(truth_path.read_text(encoding="utf-8"))]
            finding_models = [Finding.from_dict(f) for f in env.submitted_findings or []]
            rb = compute_reward(finding_models, truths, steps_used=env.steps_used)
            self.assertEqual(rb.f1, Fraction(1))
            self.assertEqual(rb.tp, 4)
            self.assertEqual(rb.fp, 0)
            self.assertEqual(rb.fn, 0)

    def test_step_budget_and_request_byte_limit(self):
        env = TwinLedgerEnv(EnvConfig(max_steps=2, max_request_bytes=256))
        env.reset(SAMPLE_EP / "public")
        self.assertTrue(env.step(_req("b1", "calc", {"expression": "1+1"}))["ok"])
        self.assertTrue(env.step(_req("b2", "calc", {"expression": "2+2"}))["ok"])
        r_lim = env.step(_req("b3", "calc", {"expression": "3+3"}))
        self.assertFalse(r_lim["ok"])
        self.assertEqual(r_lim["error"]["code"], "LIMIT")

        env2 = TwinLedgerEnv(EnvConfig(max_request_bytes=64))
        env2.reset(SAMPLE_EP / "public")
        r_big = env2.step("x" * 100)
        self.assertFalse(r_big["ok"])
        self.assertEqual(r_big["error"]["code"], "LIMIT")

    def test_jsonl_server_round_trip(self):
        requests = "\n".join(
            [
                json.dumps(_req("j1", "get_document", {"id": "company"})),
                json.dumps(_req("j2", "calc", {"expression": "round_half_even(5 * 0.5, 0)"})),
                json.dumps(_req("j3", "submit", {"findings": []})),
            ]
        ) + "\n"
        out_buf = io.StringIO()
        code = serve_stream(SAMPLE_EP / "public", io.StringIO(requests), out_buf)
        self.assertEqual(code, 0)
        lines = [json.loads(line) for line in out_buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0]["event"], "ready")
        for resp in lines[1:]:
            self.assertEqual(validate_instance("tool_response", resp), [])
            self.assertTrue(resp["ok"])
        self.assertEqual(lines[2]["result"]["result"], "2")

    def test_runtime_file_access_spy_never_touches_sealed_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pub = root / "public"
            shutil.copytree(SAMPLE_EP / "public", pub)
            priv = root / "sealed"
            priv.mkdir()
            (priv / "truth.json").write_text('{"canary": 1}\n', encoding="utf-8")

            pub_resolved = pub.resolve()
            opened: list[Path] = []
            real_io_open = io.open
            real_path_open = Path.open

            def spy_io(file, *args, **kwargs):
                if isinstance(file, (str, os.PathLike)):
                    p = Path(file).resolve()
                    if root.resolve() in p.parents or p == root.resolve():
                        opened.append(p)
                return real_io_open(file, *args, **kwargs)

            def spy_path(self_p, *args, **kwargs):
                p = self_p.resolve()
                if root.resolve() in p.parents or p == root.resolve():
                    opened.append(p)
                return real_path_open(self_p, *args, **kwargs)

            with mock.patch("io.open", side_effect=spy_io), mock.patch.object(Path, "open", spy_path):
                env = TwinLedgerEnv()
                env.reset(pub)
                env.step(_req("t1", "list_records", {"table": "invoices", "page_size": 5}))

            self.assertGreater(len(opened), 0)
            for p in opened:
                self.assertTrue(p.is_relative_to(pub_resolved), msg=f"env touched outside public/: {p}")
                self.assertNotIn("sealed", p.parts)

    def test_public_loader_rejects_dotfiles_index_hints_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pub = root / "public"
            shutil.copytree(SAMPLE_EP / "public", pub)
            (pub / "index_hints.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(EnvError):
                TwinLedgerEnv().reset(pub)

            (pub / "index_hints.json").unlink()
            (pub / ".secret").write_text("x", encoding="utf-8")
            with self.assertRaises(EnvError):
                TwinLedgerEnv().reset(pub)

            (pub / ".secret").unlink()
            outside = root / "outside.json"
            outside.write_text((pub / "company.json").read_text(encoding="utf-8"), encoding="utf-8")
            (pub / "company.json").unlink()
            (pub / "company.json").symlink_to(outside)
            with self.assertRaises(EnvError):
                TwinLedgerEnv().reset(pub)

    def test_provisional_organizer_adapter_normalizes_frozen_and_legacy(self):
        self.assertTrue(ADAPTER_PROVISIONAL)
        legacy = {
            "type": "PERIOD_CUTOFF",
            "affected_ids": ["JE-1"],
            "amount_minor": 5000,
            "currency": "KZT",
            "evidence_ids": ["INV-1", "JE-1"],
        }
        model = normalize_finding(legacy, id_namespace_map={"JE-1": "JE:JE-1", "INV-1": "INV:INV-1"})
        self.assertEqual(model.claimed_amount, 5000)
        self.assertEqual(model.affected_ids, ("JE:JE-1",))
        self.assertEqual(model.evidence_ids, ("INV:INV-1", "JE:JE-1"))

        req = normalize_tool_request({"tool": "calc", "args": {"expression": "2+2"}, "request_id": "r1"})
        self.assertEqual(req["protocol_version"], "1.0")
        self.assertEqual(req["action"]["tool"], "calc")


if __name__ == "__main__":
    unittest.main()
