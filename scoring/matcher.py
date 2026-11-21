"""Match predicate and deterministic optimal matching.

Implements Master TZ v3.0.0 sections 15.2-15.3 and Phase 6 tasks 6.3/6.4.

Match predicate (TZ 15.2, provisional pending official contract Q-005):
  1. ``type`` equals;
  2. canonical ``affected_ids`` sets are exactly equal;
  3. ``currency`` equals;
  4. ``|claimed_amount - amount_minor| <= tolerance_minor``;
  5. ``evidence_ids`` covers one complete acceptable evidence set;
  6. schema length limits and admissible typed IDs hold (checked by
     :mod:`scoring.canon` at the boundary).

``explanation`` and ``confidence`` never influence matching or reward
(TZ 15.2: no bonus for wording).

Optimal matching (TZ 15.3, REQ-SCORE-001..005): a bipartite graph with
submitted findings on the left and truth findings on the right; an edge
exists iff the predicate matches. The chosen matching

  - maximises the number of matched pairs,
  - then minimises the total absolute amount error,
  - then is the lexicographically smallest pair tuple
    ``(finding_index, truth_index)`` sorted by finding index,
  - and uses the original input index only as that final tie-break
    (REQ-SCORE-002: permutation invariance otherwise).

Implementation: min-cost max-flow (successive shortest paths, exact
integer costs) for the first two objectives, then greedy pair locking
with exact feasibility checks for the lexicographic tie-break.

This module must not import gen/, verifier/, env/ or harness/ (TZ 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from contracts.models import Finding, TruthFinding
from scoring.canon import (
    ScoringInputError,
    canonicalize_finding,
    canonicalize_truth,
    validate_findings,
    validate_truths,
)

#: Stable reason codes for predicate rejection (diagnostics-friendly).
REASON_OK = "ok"
REASON_TYPE = "type_mismatch"
REASON_AFFECTED = "affected_ids_mismatch"
REASON_CURRENCY = "currency_mismatch"
REASON_AMOUNT = "amount_out_of_tolerance"
REASON_EVIDENCE = "evidence_incomplete"

#: Bound on candidate edges for the exact lexicographic refinement step.
#: Beyond this the scorer raises a bounded error instead of silently
#: degrading determinism (episode design keeps graphs far smaller).
MAX_CANDIDATE_EDGES = 4096


@dataclass(frozen=True)
class MatchDecision:
    """Outcome of the match predicate for one (finding, truth) pair."""

    matched: bool
    reason: str
    amount_error_minor: int | None


@dataclass(frozen=True)
class MatchPair:
    """One matched (finding, truth) pair with its amount error."""

    finding_index: int
    truth_index: int
    truth_id: str
    amount_error_minor: int
    evidence_set_index: int
    evidence_set: tuple[str, ...]


@dataclass(frozen=True)
class MatchResult:
    """Complete matcher output; the only source of TP/FP/FN (REQ-SCORE-001)."""

    pairs: tuple[MatchPair, ...]
    tp: int
    fp: int
    fn: int
    findings_total: int
    truths_total: int
    candidate_edges: int
    unmatched_findings: tuple[int, ...]
    unmatched_truths: tuple[int, ...]

    def pairs_by_finding(self) -> dict[int, MatchPair]:
        return {pair.finding_index: pair for pair in self.pairs}


def match_predicate(finding: Finding, truth: TruthFinding) -> MatchDecision:
    """Evaluate the six match conditions for one finding/truth pair.

    Pure function: the same pair always yields the same decision
    (REQ-SCORE-005). Conditions are evaluated in the fixed order of TZ
    15.2 and the first failure is reported.
    """
    canon_finding = canonicalize_finding(finding)
    canon_truth = canonicalize_truth(truth)
    return _predicate_canonical(canon_finding, canon_truth)


def _predicate_canonical(canon_finding: Finding, canon_truth: TruthFinding) -> MatchDecision:
    if canon_finding.type != canon_truth.type:
        return MatchDecision(False, REASON_TYPE, None)

    if canon_finding.affected_ids != canon_truth.affected_ids:
        return MatchDecision(False, REASON_AFFECTED, None)

    if canon_finding.currency != canon_truth.currency:
        return MatchDecision(False, REASON_CURRENCY, None)

    amount_error = abs(canon_finding.claimed_amount - canon_truth.amount_minor)
    if amount_error > canon_truth.tolerance_minor:
        return MatchDecision(False, REASON_AMOUNT, amount_error)

    evidence = set(canon_finding.evidence_ids)
    for evidence_set in canon_truth.evidence_sets:
        if set(evidence_set).issubset(evidence):
            return MatchDecision(True, REASON_OK, amount_error)

    return MatchDecision(False, REASON_EVIDENCE, amount_error)


def build_edge_matrix(
    findings: Sequence[Finding], truths: Sequence[TruthFinding]
) -> tuple[list[list[int | None]], int]:
    """Build the candidate-edge matrix for validated inputs.

    Returns ``(cost, candidate_edges)`` where ``cost[i][j]`` is the
    absolute amount error of the pair when the match predicate accepts
    it, else ``None`` (forbidden edge).
    """
    canon_findings = validate_findings(findings)
    canon_truths = validate_truths(truths)
    cost, candidate_edges = _edge_matrix(canon_findings, canon_truths)
    return cost, candidate_edges


def _edge_matrix(
    canon_findings: Sequence[Finding], canon_truths: Sequence[TruthFinding]
) -> tuple[list[list[int | None]], int]:
    cost: list[list[int | None]] = []
    candidate_edges = 0
    for finding in canon_findings:
        row: list[int | None] = []
        for truth in canon_truths:
            decision = _predicate_canonical(finding, truth)
            if decision.matched:
                row.append(decision.amount_error_minor)
                candidate_edges += 1
            else:
                row.append(None)
        cost.append(row)
    return cost, candidate_edges


def optimal_pairs(cost: list[list[int | None]]) -> list[tuple[int, int]]:
    """Solve the three-level matching objective exactly.

    ``cost[i][j]`` is the secondary error (non-negative int) of pair
    ``(i, j)`` or ``None`` when the pair is forbidden. Among all
    matchings the solver picks: maximum cardinality, then minimum total
    error, then the lexicographically smallest sorted pair tuple.

    Deterministic for a fixed matrix; no dict/set iteration order leaks
    into the result.
    """
    if not cost or not cost[0]:
        return []
    n_left, n_right = _validate_cost_matrix(cost)
    if n_left == 0 or n_right == 0:
        return []

    max_pairs, min_error = _min_cost_flow(cost, min(n_left, n_right))[:2]

    # Lexicographic refinement: lock pairs greedily in (i, j) order,
    # keeping only pairs that still admit a globally optimal completion.
    locked: list[tuple[int, int]] = []
    locked_cost = 0
    used_left: set[int] = set()
    used_right: set[int] = set()

    for i in range(n_left):
        if len(locked) >= max_pairs:
            break
        if i in used_left:
            continue
        for j in range(n_right):
            if j in used_right:
                continue
            edge_error = cost[i][j]
            if edge_error is None:
                continue
            need = max_pairs - len(locked) - 1
            if need == 0:
                feasible = locked_cost + edge_error == min_error
            else:
                remaining = _sub_matrix(cost, used_left | {i}, used_right | {j})
                flow, error = _min_cost_flow(remaining, need)[:2]
                feasible = flow == need and locked_cost + edge_error + error == min_error
            if feasible:
                locked.append((i, j))
                locked_cost += edge_error
                used_left.add(i)
                used_right.add(j)
                break

    if len(locked) != max_pairs or locked_cost != min_error:
        raise ScoringInputError(
            "internal matching inconsistency: lexicographic refinement lost "
            f"optimality (pairs {len(locked)}/{max_pairs}, error "
            f"{locked_cost}/{min_error})"
        )
    return locked


def _sub_matrix(
    cost: list[list[int | None]], dead_left: set[int], dead_right: set[int]
) -> list[list[int | None]]:
    return [
        [cost[i][j] for j in range(len(cost[0])) if j not in dead_right]
        for i in range(len(cost))
        if i not in dead_left
    ]


def _validate_cost_matrix(cost: list[list[int | None]]) -> tuple[int, int]:
    if not isinstance(cost, list) or not cost:
        raise ScoringInputError("cost matrix must be a non-empty list of rows")
    n_right = len(cost[0])
    if n_right == 0:
        raise ScoringInputError("cost matrix rows must be non-empty")
    for i, row in enumerate(cost):
        if not isinstance(row, list) or len(row) != n_right:
            raise ScoringInputError(f"cost matrix row {i} has the wrong length")
        for j, value in enumerate(row):
            if value is None:
                continue
            if type(value) is not int or value < 0:
                raise ScoringInputError(
                    f"cost[{i}][{j}] must be a non-negative int or None"
                )
    return len(cost), n_right


def _min_cost_flow(
    cost: list[list[int | None]], flow_limit: int
) -> tuple[int, int, list[tuple[int, int]]]:
    """Min-cost max-flow on a bipartite unit-capacity graph.

    Successive shortest paths (SPFA/Bellman-Ford from the source; all
    original costs are non-negative ints, so the result is exact).
    Returns ``(flow_sent, total_cost, pairs)``; flow stops early when no
    augmenting path remains or ``flow_limit`` is reached.
    """
    n_left = len(cost)
    n_right = len(cost[0])
    source = 0
    left0 = 1
    right0 = left0 + n_left
    sink = right0 + n_right
    graph: list[list[list[int]]] = [[] for _ in range(sink + 1)]

    def add_edge(u: int, v: int, capacity: int, edge_cost: int) -> None:
        graph[u].append([v, len(graph[v]), capacity, edge_cost])
        graph[v].append([u, len(graph[u]) - 1, 0, -edge_cost])

    for i in range(n_left):
        add_edge(source, left0 + i, 1, 0)
    for j in range(n_right):
        add_edge(right0 + j, sink, 1, 0)
    abs_cost_bound = 1
    for i in range(n_left):
        for j in range(n_right):
            edge_error = cost[i][j]
            if edge_error is not None:
                add_edge(left0 + i, right0 + j, 1, edge_error)
                abs_cost_bound += edge_error

    total_flow = 0
    total_cost = 0
    while total_flow < flow_limit:
        # SPFA shortest augmenting path from source (residual edges may
        # carry negative costs; the current flow is min-cost for its
        # value, so no negative cycle exists).
        infinity = abs_cost_bound * (sink + 2)
        distance = [infinity] * (sink + 1)
        parent: list[tuple[int, int] | None] = [None] * (sink + 1)
        in_queue = [False] * (sink + 1)
        distance[source] = 0
        queue = [source]
        in_queue[source] = True
        while queue:
            u = queue.pop()
            in_queue[u] = False
            for edge_index, edge in enumerate(graph[u]):
                v, _, capacity, edge_cost = edge
                if capacity <= 0:
                    continue
                candidate = distance[u] + edge_cost
                if candidate < distance[v]:
                    distance[v] = candidate
                    parent[v] = (u, edge_index)
                    if not in_queue[v]:
                        in_queue[v] = True
                        queue.append(v)
        if parent[sink] is None:
            break
        node = sink
        while node != source:
            u, edge_index = parent[node]  # type: ignore[misc]
            edge = graph[u][edge_index]
            edge[2] -= 1
            graph[node][edge[1]][2] += 1
            node = u
        total_flow += 1
        total_cost += distance[sink]

    pairs: list[tuple[int, int]] = []
    for i in range(n_left):
        for edge in graph[left0 + i]:
            v, _, capacity, _ = edge
            if right0 <= v < right0 + n_right and capacity == 0:
                pairs.append((i, v - right0))
    pairs.sort()
    return total_flow, total_cost, pairs


def optimal_matching(
    findings: Sequence[Finding], truths: Sequence[TruthFinding]
) -> MatchResult:
    """Match submitted findings against truth deterministically.

    This is the only definition of TP/FP/FN in the project
    (REQ-SCORE-001): ``tp = |pairs|``, ``fp = |findings| - tp``,
    ``fn = |truths| - tp``. Duplicates, split findings and extra output
    can never inflate TP beyond the number of truths (REQ-SCORE-003,
    REQ-SCORE-004).
    """
    canon_findings = validate_findings(findings)
    canon_truths = validate_truths(truths)
    cost, candidate_edges = _edge_matrix(canon_findings, canon_truths)
    if candidate_edges > MAX_CANDIDATE_EDGES:
        raise ScoringInputError(
            f"too many candidate edges ({candidate_edges}) for the exact "
            f"deterministic matcher (limit {MAX_CANDIDATE_EDGES})"
        )
    pairs_raw = optimal_pairs(cost)
    pairs: list[MatchPair] = []
    for i, j in pairs_raw:
        truth = canon_truths[j]
        evidence = set(canon_findings[i].evidence_ids)
        evidence_set_index = -1
        evidence_set: tuple[str, ...] = ()
        for set_index, candidate_set in enumerate(truth.evidence_sets):
            if set(candidate_set).issubset(evidence):
                evidence_set_index = set_index
                evidence_set = candidate_set
                break
        pairs.append(
            MatchPair(
                finding_index=i,
                truth_index=j,
                truth_id=truth.truth_id,
                amount_error_minor=cost[i][j] or 0,
                evidence_set_index=evidence_set_index,
                evidence_set=evidence_set,
            )
        )
    tp = len(pairs)
    matched_findings = {pair.finding_index for pair in pairs}
    matched_truths = {pair.truth_index for pair in pairs}
    return MatchResult(
        pairs=tuple(pairs),
        tp=tp,
        fp=len(canon_findings) - tp,
        fn=len(canon_truths) - tp,
        findings_total=len(canon_findings),
        truths_total=len(canon_truths),
        candidate_edges=candidate_edges,
        unmatched_findings=tuple(
            i for i in range(len(canon_findings)) if i not in matched_findings
        ),
        unmatched_truths=tuple(
            j for j in range(len(canon_truths)) if j not in matched_truths
        ),
    )


__all__ = [
    "MatchDecision",
    "MatchPair",
    "MatchResult",
    "MAX_CANDIDATE_EDGES",
    "REASON_OK",
    "REASON_TYPE",
    "REASON_AFFECTED",
    "REASON_CURRENCY",
    "REASON_AMOUNT",
    "REASON_EVIDENCE",
    "match_predicate",
    "build_edge_matrix",
    "optimal_pairs",
    "optimal_matching",
]
