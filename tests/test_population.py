import unittest

from pokequant.analysis.population import generate_opponent_population, pair_association
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
        # The strongest usage/association core should survive into the top proposal.
        self.assertTrue({"A", "B", "C"}.issubset(set(rows[0].members)))


if __name__ == "__main__":
    unittest.main()
