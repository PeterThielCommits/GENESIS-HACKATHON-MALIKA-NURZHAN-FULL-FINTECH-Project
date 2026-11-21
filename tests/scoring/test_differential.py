"""Brute-force differential matcher tests (Phase 6 task 6.7, TZ 15.3).

Random small bipartite graphs (up to 7x7, seeded and reproducible,
REQ-TEST-003) are solved by both the production min-cost-flow matcher
and the independent exhaustive oracle; the results are compared on the
two primary criteria (max pairs, min total error) and, for tiny graphs,
on the lexicographic tie-break as well.
"""

from __future__ import annotations

import random
import unittest

from scoring.exhaustive import exhaustive_lex_best, exhaustive_optimum
from scoring.matcher import optimal_pairs


def random_cost_matrix(rng: random.Random, n_left: int, n_right: int, density: float):
    cost: list[list[int | None]] = []
    for _ in range(n_left):
        row: list[int | None] = []
        for _ in range(n_right):
            if rng.random() < density:
                row.append(rng.randint(0, 9))
            else:
                row.append(None)
        cost.append(row)
    return cost


class TestDifferential(unittest.TestCase):
    def test_random_graphs_up_to_7x7(self):
        # Deterministic corpus: fixed seeds (REQ-TEST-003).
        for seed in range(60):
            rng = random.Random(seed)
            n_left = rng.randint(1, 7)
            n_right = rng.randint(1, 7)
            density = rng.choice([0.35, 0.6, 0.85, 1.0])
            cost = random_cost_matrix(rng, n_left, n_right, density)

            pairs = optimal_pairs(cost)
            flow = len(pairs)
            error = sum(cost[i][j] for i, j in pairs)  # type: ignore[misc]
            best_flow, best_error = exhaustive_optimum(cost)

            with self.subTest(seed=seed, n=(n_left, n_right), density=density):
                self.assertEqual(flow, best_flow, "matcher lost cardinality")
                self.assertEqual(error, best_error, "matcher lost error optimality")

    def test_tie_break_matches_exhaustive_on_tiny_graphs(self):
        for seed in range(40):
            rng = random.Random(1000 + seed)
            n_left = rng.randint(1, 4)
            n_right = rng.randint(1, 4)
            density = rng.choice([0.5, 1.0])
            cost = random_cost_matrix(rng, n_left, n_right, density)

            pairs = optimal_pairs(cost)
            expected = exhaustive_lex_best(cost)
            with self.subTest(seed=seed):
                self.assertEqual(pairs, list(expected))

    def test_tiny_known_graphs(self):
        cases = [
            ([[5]], [(0, 0)]),
            ([[None]], []),
            ([[0, 0]], [(0, 0)]),
            ([[3, 1], [2, 2]], [(0, 1), (1, 0)]),
            # Total-error tie (15 vs 15): the lexicographic pair tuple
            # decides in favour of [(0,0),(1,1)].
            ([[9, 8], [7, 6]], [(0, 0), (1, 1)]),
            # Minimum total error is 4 via (0,0)+(1,2)+(2,1).
            ([[1, 2, 3], [3, 2, 1], [2, 2, 2]], [(0, 0), (1, 2), (2, 1)]),
        ]
        for cost, expected in cases:
            with self.subTest(cost=cost):
                self.assertEqual(optimal_pairs(cost), expected)
                self.assertEqual(
                    (len(expected), sum(cost[i][j] for i, j in expected)),  # type: ignore[misc]
                    exhaustive_optimum(cost),
                )

    def test_oracle_agrees_with_itself(self):
        # Sanity for the oracle: exhaustive optimum is achievable.
        for seed in range(10):
            rng = random.Random(5000 + seed)
            cost = random_cost_matrix(rng, 3, 3, 0.7)
            best_flow, best_error = exhaustive_optimum(cost)
            lex = exhaustive_lex_best(cost)
            self.assertEqual(len(lex), best_flow)
            self.assertEqual(sum(cost[i][j] for i, j in lex), best_error)  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
