"""Exhaustive reference matcher for small bipartite graphs.

Phase 6 task 6.7 / TZ 15.3: a brute-force oracle used by differential
tests to cross-check :func:`scoring.matcher.optimal_pairs` on the two
primary criteria (maximum matched pairs, minimum total amount error)
and, for tiny graphs, on the lexicographic tie-break as well.

Only for small graphs (the enumeration is factorial); the production
matcher is :mod:`scoring.matcher`. This module is deliberately
independent of the min-cost-flow implementation: it enumerates partial
matchings directly, so a shared bug cannot hide in both.
"""

from __future__ import annotations

from typing import Iterable

from scoring.canon import ScoringInputError


def _validate(cost: list[list[int | None]]) -> tuple[int, int]:
    if not isinstance(cost, list) or not cost:
        raise ScoringInputError("cost matrix must be a non-empty list of rows")
    n_right = len(cost[0])
    if n_right == 0:
        raise ScoringInputError("cost matrix rows must be non-empty")
    for i, row in enumerate(cost):
        if not isinstance(row, list) or len(row) != n_right:
            raise ScoringInputError(f"cost matrix row {i} has the wrong length")
        for j, value in enumerate(row):
            if value is not None and (type(value) is not int or value < 0):
                raise ScoringInputError(
                    f"cost[{i}][{j}] must be a non-negative int or None"
                )
    return len(cost), n_right


def _all_matchings(cost: list[list[int | None]]) -> Iterable[tuple[tuple[int, int], ...]]:
    """Yield every matching (as sorted pair tuples), including the empty one."""
    n_left, n_right = _validate(cost)

    def extend(i: int, used_right: tuple[int, ...], pairs: tuple[tuple[int, int], ...]):
        if i == n_left:
            yield pairs
            return
        yield from extend(i + 1, used_right, pairs)
        for j in range(n_right):
            if cost[i][j] is None or j in used_right:
                continue
            yield from extend(i + 1, used_right + (j,), pairs + ((i, j),))

    yield from extend(0, tuple(), tuple())


def exhaustive_optimum(cost: list[list[int | None]]) -> tuple[int, int]:
    """Return ``(max_pairs, min_total_error)`` by full enumeration."""
    best_pairs = 0
    best_error = 0
    for pairs in _all_matchings(cost):
        size = len(pairs)
        error = sum(cost[i][j] for i, j in pairs)  # type: ignore[misc]
        if size > best_pairs or (size == best_pairs and error < best_error):
            best_pairs, best_error = size, error
    return best_pairs, best_error


def exhaustive_lex_best(cost: list[list[int | None]]) -> tuple[tuple[int, int], ...]:
    """Return the lexicographically smallest optimal matching.

    Same three-level objective as the production matcher: maximum
    pairs, then minimum total error, then smallest sorted pair tuple.
    Intended for graphs up to roughly 5x5 in tests.
    """
    best_pairs = 0
    best_error = 0
    best_matching: tuple[tuple[int, int], ...] = tuple()
    for pairs in _all_matchings(cost):
        size = len(pairs)
        error = sum(cost[i][j] for i, j in pairs)  # type: ignore[misc]
        if size > best_pairs or (size == best_pairs and error < best_error):
            best_pairs, best_error = size, error
            best_matching = pairs
        elif size == best_pairs and error == best_error and pairs < best_matching:
            best_matching = pairs
    return best_matching


__all__ = ["exhaustive_optimum", "exhaustive_lex_best"]
