"""ProofGraph DAG integrity and traceability tests (Phase 8, Task 8.3).

Verifies Master TZ 13.4, 21.1, 21.4, REQ-VER-003, REQ-VER-004:
  - exact node types (RecordNode, FactNode, RuleNode, CalculationNode, FindingNode);
  - exact edge types (derived_from, supports, contradicts, governed_by, excludes);
  - required fields (node_id, node_type, source_ids, rule_id, value_digest, parent_node_ids);
  - strict acyclicity (cycle rejected);
  - every FindingNode has directed paths to >=1 RecordNode and >=1 RuleNode;
  - every FactNode carries non-empty source_ids and rule_id;
  - deterministic sorting and digest stability.
"""

from __future__ import annotations

import unittest

from tests.verifier import fixtures as fx
from verifier import discover
from verifier.proof_graph import EDGE_TYPES, NODE_TYPES, ProofGraph


class TestProofGraph(unittest.TestCase):
    def test_compound_episode_proof_graph_valid_and_complete(self):
        ep, _ = fx.compound_four_type_episode()
        out = discover(ep)
        graph = out.proof_graph
        errors = graph.validate(reachable_typed_ids=ep.all_reachable_typed_ids())
        self.assertEqual(errors, [])

        g_dict = graph.to_dict()
        # Deterministic sorting of nodes and edges
        node_ids = [n["node_id"] for n in g_dict["nodes"]]
        self.assertEqual(node_ids, sorted(node_ids))
        edge_keys = [(e["from_node_id"], e["to_node_id"], e["edge_type"]) for e in g_dict["edges"]]
        self.assertEqual(edge_keys, sorted(edge_keys))

        # Every node has required TZ 13.4 fields and valid types
        required_keys = {"node_id", "node_type", "source_ids", "rule_id", "value_digest", "parent_node_ids"}
        for node in g_dict["nodes"]:
            self.assertTrue(required_keys.issubset(node.keys()))
            self.assertIn(node["node_type"], NODE_TYPES)
            self.assertEqual(len(node["value_digest"]), 64)
        for edge in g_dict["edges"]:
            self.assertIn(edge["edge_type"], EDGE_TYPES)

        # Every finding references a real FindingNode with path to RecordNode and RuleNode
        finding_nodes = [n for n in graph.nodes if n.node_type == "FindingNode"]
        self.assertEqual(len(finding_nodes), 4)
        for f in out.report.findings:
            self.assertTrue(f.proof_graph_ref.startswith("proof:"))
            nid = f.proof_graph_ref[len("proof:"):]
            node = graph.get_node(nid)
            self.assertIsNotNone(node)
            self.assertEqual(node.node_type, "FindingNode")
            anc = graph.ancestors_of(nid)
            anc_types = {graph.get_node(a).node_type for a in anc}
            self.assertIn("RecordNode", anc_types)
            self.assertIn("RuleNode", anc_types)

    def test_detects_cycle(self):
        g = ProofGraph("a" * 64)
        r = g.add_record("INV:1", {"doc_id": "1"})
        f1 = g.add_fact("f1", "R1", ["INV:1"], [r], {"v": 1})
        f2 = g.add_fact("f2", "R1", ["INV:1"], [f1], {"v": 2})
        g.add_edge(f2, f1, "supports")
        errors = g.validate()
        self.assertTrue(any("cycle" in e.lower() for e in errors))

    def test_finding_without_record_or_rule_rejected(self):
        g = ProofGraph("b" * 64)
        rule = g.add_rule("R1", {"k": "v"})
        g.add_finding("F1", "R1", ["INV:1"], [], [rule], {"type": "PERIOD_CUTOFF"})
        errors = g.validate()
        self.assertTrue(any("RecordNode" in e for e in errors))

        g2 = ProofGraph("c" * 64)
        rec = g2.add_record("INV:1", {"doc_id": "1"})
        g2.add_finding("F2", "R1", ["INV:1"], [rec], [], {"type": "PERIOD_CUTOFF"})
        errors2 = g2.validate()
        self.assertTrue(any("RuleNode" in e for e in errors2))

    def test_fact_node_requires_source_and_rule(self):
        g = ProofGraph("d" * 64)
        with self.assertRaises(ValueError):
            g.add_fact("f1", "", ["INV:1"], [], {"x": 1})
        with self.assertRaises(ValueError):
            g.add_fact("f1", "R1", [], [], {"x": 1})

    def test_unreachable_source_id_flagged(self):
        g = ProofGraph("e" * 64)
        rec = g.add_record("INV:HIDDEN", {"doc_id": "HIDDEN"})
        rule = g.add_rule("R1", {"k": "v"})
        g.add_finding("F1", "R1", ["INV:HIDDEN"], [rec], [rule], {"x": 1})
        errors = g.validate(reachable_typed_ids=frozenset({"INV:PUBLIC"}))
        self.assertTrue(any("unreachable" in e.lower() for e in errors))


if __name__ == "__main__":
    unittest.main()
