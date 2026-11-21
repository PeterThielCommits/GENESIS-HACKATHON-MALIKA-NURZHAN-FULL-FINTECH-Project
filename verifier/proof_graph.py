"""Deterministic ProofGraph DAG for the independent verifier (TZ 13.4, 21.1, 21.4).

Node types:
  - ``RecordNode``       public record/document
  - ``FactNode``         verifiable extracted fact
  - ``RuleNode``         accounting policy / normative rule
  - ``CalculationNode``  deterministic calculation
  - ``FindingNode``      discovered anomaly finding

Edge types:
  - ``derived_from``
  - ``supports``
  - ``contradicts``
  - ``governed_by``
  - ``excludes``

Every node carries ``node_id``, ``node_type``, ``source_ids``, ``rule_id``,
``value_digest``, and ``parent_node_ids`` (TZ 13.4), sorted deterministically.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from contracts.canonical import canonicalize, sha256_hex

NODE_TYPES: tuple[str, ...] = (
    "RecordNode",
    "FactNode",
    "RuleNode",
    "CalculationNode",
    "FindingNode",
)

EDGE_TYPES: tuple[str, ...] = (
    "derived_from",
    "supports",
    "contradicts",
    "governed_by",
    "excludes",
)

PUBLIC_CONTEXT_SOURCES: frozenset[str] = frozenset(
    {
        "company.json",
        "policy.json",
        "accounts.json",
        "opening_balances.json",
        "period_calendar.json",
    }
)


@dataclass(frozen=True)
class ProofNode:
    node_id: str
    node_type: str
    source_ids: tuple[str, ...]
    rule_id: str
    value_digest: str
    parent_node_ids: tuple[str, ...]
    label: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "source_ids": list(self.source_ids),
            "rule_id": self.rule_id,
            "value_digest": self.value_digest,
            "parent_node_ids": list(self.parent_node_ids),
            "label": self.label,
            "payload": canonicalize(self.payload),
        }


@dataclass(frozen=True)
class ProofEdge:
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type,
        }


class ProofGraph:
    """Mutable builder / immutable-serializable deterministic ProofGraph DAG."""

    def __init__(self, episode_public_hash: str) -> None:
        self.episode_public_hash = episode_public_hash
        self._nodes: dict[str, ProofNode] = {}
        self._edges: dict[tuple[str, str, str], ProofEdge] = {}

    def add_record(self, typed_id: str, record: Mapping[str, Any], label: str = "") -> str:
        node_id = f"rec:{typed_id}"
        if node_id not in self._nodes:
            digest = sha256_hex(canonicalize(dict(record)))
            self._nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type="RecordNode",
                source_ids=(typed_id,),
                rule_id="",
                value_digest=digest,
                parent_node_ids=(),
                label=label or typed_id,
                payload={"typed_id": typed_id},
            )
        return node_id

    def add_rule(
        self,
        rule_id: str,
        payload: Mapping[str, Any],
        source_files: Iterable[str] = ("policy.json",),
        label: str = "",
    ) -> str:
        node_id = f"rule:{rule_id}"
        if node_id not in self._nodes:
            sources = tuple(sorted(set(source_files)))
            digest = sha256_hex(canonicalize(dict(payload)))
            self._nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type="RuleNode",
                source_ids=sources,
                rule_id=rule_id,
                value_digest=digest,
                parent_node_ids=(),
                label=label or rule_id,
                payload=canonicalize(dict(payload)),
            )
        return node_id

    def add_fact(
        self,
        fact_key: str,
        rule_id: str,
        source_ids: Iterable[str],
        parent_node_ids: Iterable[str],
        payload: Mapping[str, Any],
        label: str = "",
        edge_type: str = "derived_from",
    ) -> str:
        if not rule_id:
            raise ValueError("FactNode requires a non-empty rule_id (REQ-VER-004)")
        sources = tuple(sorted(set(source_ids)))
        if not sources:
            raise ValueError("FactNode requires non-empty source_ids (REQ-VER-004)")
        parents = tuple(sorted(set(parent_node_ids)))
        digest = sha256_hex(canonicalize(dict(payload)))
        node_id = f"fact:{fact_key}:{digest[:12]}"
        if node_id not in self._nodes:
            self._nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type="FactNode",
                source_ids=sources,
                rule_id=rule_id,
                value_digest=digest,
                parent_node_ids=parents,
                label=label or fact_key,
                payload=canonicalize(dict(payload)),
            )
        for pid in parents:
            self.add_edge(pid, node_id, edge_type)
        return node_id

    def add_calculation(
        self,
        calc_key: str,
        rule_id: str,
        source_ids: Iterable[str],
        parent_node_ids: Iterable[str],
        payload: Mapping[str, Any],
        label: str = "",
        governed_by_nodes: Iterable[str] = (),
    ) -> str:
        sources = tuple(sorted(set(source_ids)))
        gov = tuple(sorted(set(governed_by_nodes)))
        parents = tuple(sorted(set(parent_node_ids) | set(gov)))
        digest = sha256_hex(canonicalize(dict(payload)))
        node_id = f"calc:{calc_key}:{digest[:12]}"
        if node_id not in self._nodes:
            self._nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type="CalculationNode",
                source_ids=sources,
                rule_id=rule_id,
                value_digest=digest,
                parent_node_ids=parents,
                label=label or calc_key,
                payload=canonicalize(dict(payload)),
            )
        for pid in parent_node_ids:
            self.add_edge(pid, node_id, "derived_from")
        for gid in gov:
            self.add_edge(gid, node_id, "governed_by")
        return node_id

    def add_finding(
        self,
        finding_key: str,
        rule_id: str,
        source_ids: Iterable[str],
        supporting_node_ids: Iterable[str],
        governed_by_nodes: Iterable[str],
        payload: Mapping[str, Any],
        label: str = "",
    ) -> str:
        sources = tuple(sorted(set(source_ids)))
        sup = tuple(sorted(set(supporting_node_ids)))
        gov = tuple(sorted(set(governed_by_nodes)))
        parents = tuple(sorted(set(sup) | set(gov)))
        digest = sha256_hex(canonicalize(dict(payload)))
        node_id = f"finding:{finding_key}:{digest[:12]}"
        if node_id not in self._nodes:
            self._nodes[node_id] = ProofNode(
                node_id=node_id,
                node_type="FindingNode",
                source_ids=sources,
                rule_id=rule_id,
                value_digest=digest,
                parent_node_ids=parents,
                label=label or finding_key,
                payload=canonicalize(dict(payload)),
            )
        for sid in sup:
            self.add_edge(sid, node_id, "supports")
        for gid in gov:
            self.add_edge(gid, node_id, "governed_by")
        return node_id

    def add_edge(self, from_node_id: str, to_node_id: str, edge_type: str) -> str:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"unknown ProofGraph edge_type: {edge_type!r}")
        if from_node_id == to_node_id:
            raise ValueError(f"self-loop forbidden in ProofGraph: {from_node_id!r}")
        key = (from_node_id, to_node_id, edge_type)
        if key not in self._edges:
            edge_id = f"edge:{sha256_hex({'f': from_node_id, 't': to_node_id, 'e': edge_type})[:16]}"
            self._edges[key] = ProofEdge(
                edge_id=edge_id,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
                edge_type=edge_type,
            )
        return self._edges[key].edge_id

    def record_exclusion(
        self,
        distractor_code: str,
        candidate_node_id: str,
        excluding_node_ids: Iterable[str],
        rule_node_id: str | None = None,
        edge_type: str = "excludes",
    ) -> None:
        """Record an explicit contradiction/exclusion edge for a distractor."""
        if edge_type not in ("contradicts", "excludes"):
            raise ValueError("exclusion edge_type must be 'contradicts' or 'excludes'")
        for ex_id in sorted(set(excluding_node_ids)):
            if ex_id != candidate_node_id:
                self.add_edge(ex_id, candidate_node_id, edge_type)
        if rule_node_id is not None and rule_node_id != candidate_node_id:
            self.add_edge(rule_node_id, candidate_node_id, "governed_by")

    @property
    def nodes(self) -> tuple[ProofNode, ...]:
        return tuple(self._nodes[k] for k in sorted(self._nodes))

    @property
    def edges(self) -> tuple[ProofEdge, ...]:
        return tuple(self._edges[k] for k in sorted(self._edges))

    def get_node(self, node_id: str) -> ProofNode | None:
        return self._nodes.get(node_id)

    def exclusion_edges(self) -> tuple[ProofEdge, ...]:
        return tuple(
            e for e in self.edges if e.edge_type in ("contradicts", "excludes")
        )

    def ancestors_of(self, node_id: str) -> set[str]:
        """Return all upstream node_ids reaching ``node_id`` via edges."""
        reverse_adj: dict[str, set[str]] = {}
        for edge in self._edges.values():
            reverse_adj.setdefault(edge.to_node_id, set()).add(edge.from_node_id)
        for node in self._nodes.values():
            for pid in node.parent_node_ids:
                reverse_adj.setdefault(node.node_id, set()).add(pid)
        visited: set[str] = set()
        queue: deque[str] = deque([node_id])
        while queue:
            curr = queue.popleft()
            for prev in reverse_adj.get(curr, ()):
                if prev not in visited:
                    visited.add(prev)
                    queue.append(prev)
        return visited

    def validate(self, reachable_typed_ids: frozenset[str] | None = None) -> list[str]:
        """Validate DAG acyclicity and REQ-VER-003/REQ-VER-004 invariants."""
        errors: list[str] = []

        # 1. Validate node fields and references
        for node in self.nodes:
            if node.node_type not in NODE_TYPES:
                errors.append(f"node {node.node_id}: unknown type {node.node_type!r}")
            if len(node.value_digest) != 64:
                errors.append(f"node {node.node_id}: invalid value_digest")
            for pid in node.parent_node_ids:
                if pid not in self._nodes:
                    errors.append(f"node {node.node_id}: missing parent {pid!r}")
            if node.node_type == "FactNode":
                if not node.source_ids:
                    errors.append(f"FactNode {node.node_id}: empty source_ids (REQ-VER-004)")
                if not node.rule_id:
                    errors.append(f"FactNode {node.node_id}: empty rule_id (REQ-VER-004)")
            if reachable_typed_ids is not None:
                for sid in node.source_ids:
                    if sid not in PUBLIC_CONTEXT_SOURCES and sid not in reachable_typed_ids:
                        errors.append(
                            f"node {node.node_id}: unreachable source_id {sid!r}"
                        )

        # 2. Validate edge endpoints
        adj: dict[str, list[str]] = {nid: [] for nid in self._nodes}
        in_degree: dict[str, int] = {nid: 0 for nid in self._nodes}
        seen_dir_edges: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.from_node_id not in self._nodes:
                errors.append(f"edge {edge.edge_id}: missing from_node_id {edge.from_node_id!r}")
                continue
            if edge.to_node_id not in self._nodes:
                errors.append(f"edge {edge.edge_id}: missing to_node_id {edge.to_node_id!r}")
                continue
            pair = (edge.from_node_id, edge.to_node_id)
            if pair not in seen_dir_edges:
                seen_dir_edges.add(pair)
                adj[edge.from_node_id].append(edge.to_node_id)
                in_degree[edge.to_node_id] += 1

        # 3. Acyclicity (Kahn's topological sort)
        q: deque[str] = deque(sorted(nid for nid, deg in in_degree.items() if deg == 0))
        visited_count = 0
        while q:
            u = q.popleft()
            visited_count += 1
            for v in sorted(adj[u]):
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    q.append(v)
        if visited_count != len(self._nodes):
            errors.append("ProofGraph contains a cycle (must be a strict DAG)")

        # 4. Every FindingNode must trace back to >=1 RecordNode and >=1 RuleNode (REQ-VER-003)
        for node in self.nodes:
            if node.node_type == "FindingNode":
                ancestors = self.ancestors_of(node.node_id)
                anc_types = {self._nodes[a].node_type for a in ancestors if a in self._nodes}
                if "RecordNode" not in anc_types:
                    errors.append(
                        f"FindingNode {node.node_id}: no path to any public RecordNode (REQ-VER-003)"
                    )
                if "RuleNode" not in anc_types:
                    errors.append(
                        f"FindingNode {node.node_id}: no path to any RuleNode (REQ-VER-003)"
                    )

        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "episode_public_hash": self.episode_public_hash,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def digest(self) -> str:
        return sha256_hex(self.to_dict())


__all__ = [
    "EDGE_TYPES",
    "NODE_TYPES",
    "PUBLIC_CONTEXT_SOURCES",
    "ProofEdge",
    "ProofGraph",
    "ProofNode",
]
