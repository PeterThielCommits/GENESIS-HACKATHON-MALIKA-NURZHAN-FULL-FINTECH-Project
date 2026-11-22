"""Independent ProofGraph DAG (spec §4) — second derivation.

A small but real graph: five node types, five edge types, deterministic node
ids, strict DAG check, and the invariant that every finding has directed paths
from at least one record node and one rule node.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

NODE_TYPES = ("RecordNode", "FactNode", "RuleNode", "CalculationNode", "FindingNode")
EDGE_TYPES = ("derived_from", "supports", "contradicts", "governed_by", "excludes")


@dataclass
class ProofNode:
    node_id: str
    node_type: str
    source_ids: tuple[str, ...]
    rule_id: str
    value_digest: str
    parent_node_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "source_ids": list(self.source_ids),
            "rule_id": self.rule_id,
            "value_digest": self.value_digest,
            "parent_node_ids": list(self.parent_node_ids),
        }


@dataclass
class ProofEdge:
    from_node_id: str
    to_node_id: str
    edge_type: str

    def to_dict(self) -> dict:
        return {
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
        }


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


@dataclass
class ProofGraph:
    nodes: dict[str, ProofNode] = field(default_factory=dict)
    edges: list[ProofEdge] = field(default_factory=list)
    _edge_set: set[tuple[str, str, str]] = field(default_factory=set)

    def add_node(
        self,
        node_type: str,
        source_ids,
        rule_id: str,
        parents,
        value_note: str = "",
    ) -> str:
        if node_type not in NODE_TYPES:
            raise ValueError(f"unknown node_type {node_type!r}")
        srcs = tuple(sorted(str(s) for s in source_ids))
        parent_ids = tuple(sorted(p for p in parents))
        seed = f"{node_type}|{','.join(srcs)}|{rule_id}|{','.join(parent_ids)}|{value_note}"
        digest = _digest(seed)
        node_id = f"{node_type.lower()}:{digest[:24]}"
        if node_id not in self.nodes:
            self.nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type=node_type,
                source_ids=srcs,
                rule_id=rule_id,
                value_digest=digest,
                parent_node_ids=parent_ids,
            )
            for parent in parent_ids:
                self.add_edge(parent, node_id, "derived_from")
        return node_id

    def add_edge(self, from_node_id: str, to_node_id: str, edge_type: str) -> None:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"unknown edge_type {edge_type!r}")
        key = (from_node_id, to_node_id, edge_type)
        if key not in self._edge_set:
            self._edge_set.add(key)
            self.edges.append(ProofEdge(from_node_id, to_node_id, edge_type))

    def add_excludes(self, from_node_id: str, to_node_id: str) -> None:
        self.add_edge(from_node_id, to_node_id, "excludes")

    def add_supports(self, from_node_id: str, to_node_id: str) -> None:
        self.add_edge(from_node_id, to_node_id, "supports")

    def add_governed_by(self, from_node_id: str, rule_node_id: str) -> None:
        self.add_edge(from_node_id, rule_node_id, "governed_by")

    # -- invariants --------------------------------------------------------
    def check_invariants(self) -> list[str]:
        errors: list[str] = []
        # 1. Strict DAG: Kahn's algorithm over the node set.
        indegree = {nid: 0 for nid in self.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            if edge.from_node_id in indegree and edge.to_node_id in indegree:
                adjacency[edge.from_node_id].append(edge.to_node_id)
                indegree[edge.to_node_id] += 1
        queue = sorted(nid for nid, deg in indegree.items() if deg == 0)
        seen = 0
        while queue:
            nid = queue.pop(0)
            seen += 1
            for nxt in sorted(adjacency[nid]):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if seen != len(self.nodes):
            errors.append("graph contains a cycle")
        # 2. Every FindingNode has directed paths from >=1 RecordNode and >=1 RuleNode.
        parents_of: dict[str, set[str]] = {nid: set() for nid in self.nodes}
        for edge in self.edges:
            if edge.edge_type in ("derived_from", "supports", "governed_by"):
                parents_of[edge.to_node_id].add(edge.from_node_id)
        for nid, node in self.nodes.items():
            if node.node_type != "FindingNode":
                continue
            ancestors: set[str] = set()
            stack = list(parents_of[nid])
            while stack:
                cur = stack.pop()
                if cur in ancestors:
                    continue
                ancestors.add(cur)
                stack.extend(parents_of.get(cur, ()))
            has_record = any(self.nodes[a].node_type == "RecordNode" for a in ancestors)
            has_rule = any(self.nodes[a].node_type == "RuleNode" for a in ancestors)
            if not has_record:
                errors.append(f"{nid}: no RecordNode ancestor")
            if not has_rule:
                errors.append(f"{nid}: no RuleNode ancestor")
        # 3. Every FactNode has non-empty source_ids and rule_id.
        for node in self.nodes.values():
            if node.node_type == "FactNode" and (not node.source_ids or not node.rule_id):
                errors.append(f"{node.node_id}: FactNode lacks source_ids or rule_id")
        return errors

    # -- determinism ---------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in sorted(self.nodes.values(), key=lambda n: n.node_id)],
            "edges": [
                e.to_dict()
                for e in sorted(
                    self.edges, key=lambda e: (e.from_node_id, e.to_node_id, e.edge_type)
                )
            ],
        }

    def ref(self) -> str:
        import json

        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
