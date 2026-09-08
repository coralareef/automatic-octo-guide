import itertools
import unittest

from pokequant.analysis.population import (
    generate_opponent_population,
    pair_association,
    team_swap_distance,
)
from pokequant.models import PokemonMeta


class OpponentPopulationTests(unittest.TestCase):
    def _records(self):
        names = ["A", "B", "C", "D", "E", "F", "G"]
        records = {}
        for idx, name in enumerate(names):
            teammates = {}
            for other in names:
                if other == name:
                    continue
                # A-B-C form a strong core; remaining pairs have weak evidence.
                if name in {"A", "B", "C"} and other in {"A", "B", "C"}:
                    teammates[other] = 100.0
                else:
                    teammates[other] = 5.0
            records[name] = PokemonMeta(
                name=name,
                usage=0.30 - idx * 0.02,
                teammates=teammates,
            )
        return records

    def test_pair_association_is_bounded_and_rewards_strong_pair(self):
        records = self._records()
        strong = pair_association(records["A"], records["B"])
        weak = pair_association(records["A"], records["D"])
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(weak, 0.0)
        self.assertLessEqual(strong, 1.0)

    def test_population_is_unique_normalized_and_coherent(self):
        records = self._records()
        rows = generate_opponent_population(
            records,
            pool_size=7,
            beam_width=100,
            team_size=6,
            top=5,
        )
        self.assertTrue(rows)
        self.assertAlmostEqual(sum(row.proposal_probability for row in rows), 1.0, places=7)
        self.assertEqual(len({row.members for row in rows}), len(rows))
        self.assertTrue(all(len(row.members) == 6 for row in rows))
        # The strongest usage/association core should survive somewhere in the prototypes.
        self.assertTrue(any({"A", "B", "C"}.issubset(set(row.members)) for row in rows))

    def test_prototypes_diversify_when_roster_space_allows(self):
        names = list("ABCDEFGHIJKL")
        records = {}
        for idx, name in enumerate(names):
            teammates = {other: 10.0 for other in names if other != name}
            records[name] = PokemonMeta(
                name=name,
                usage=0.40 - idx * 0.015,
                teammates=teammates,
            )
        rows = generate_opponent_population(
            records,
            pool_size=12,
            beam_width=500,
            team_size=4,
            top=5,
            candidate_multiplier=8,
            min_prototype_swaps=2,
            diversity_strength=2.0,
        )
        self.assertEqual(len(rows), 5)
        distances = [
            team_swap_distance(a.members, b.members)
            for a, b in itertools.combinations(rows, 2)
        ]
        self.assertGreaterEqual(min(distances), 1)
        self.assertGreaterEqual(sum(distance >= 2 for distance in distances), 4)
        self.assertAlmostEqual(sum(row.proposal_probability for row in rows), 1.0, places=7)


if __name__ == "__main__":
    unittest.main()
