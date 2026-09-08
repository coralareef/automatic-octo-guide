import unittest

from pokequant.analysis.meta import rank_pokemon
from pokequant.models import PokemonMeta
from pokequant.optimizer.team import (
    beam_search,
    roster_swap_distance,
    select_diverse_candidates,
    single_swap_mutations,
)


class OptimizerTests(unittest.TestCase):
    def _records(self, names):
        records = {}
        for i, name in enumerate(names):
            records[name] = PokemonMeta(
                name=name,
                usage=100 - i,
                raw_count=100,
                moves={"move1": 70, "move2": 30},
                items={"item1": 100},
                tera_types={"Water": 50, "Steel": 50},
                teammates={other: 20 for other in names if other != name},
            )
        return records

    def test_returns_six_unique_members(self):
        names = ["A", "B", "C", "D", "E", "F", "G"]
        records = self._records(names)
        ranked = rank_pokemon(records)
        result = beam_search(records, ranked, pool_size=7, beam_width=30)
        self.assertTrue(result)
        self.assertEqual(len(result[0].members), 6)
        self.assertEqual(len(set(result[0].members)), 6)

    def test_single_swap_mutations_change_exactly_one_slot(self):
        names = list("ABCDEFGHIJ")
        records = self._records(names)
        ranked = rank_pokemon(records)
        incumbent = tuple(names[:6])
        rows = single_swap_mutations(
            incumbent,
            records,
            ranked,
            pool_size=10,
            per_slot=1,
        )
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 6)
        self.assertTrue(all(roster_swap_distance(incumbent, row.members) == 1 for row in rows))
        self.assertTrue(all(len(set(row.members)) == 6 for row in rows))

    def test_diverse_frontier_avoids_only_near_clones_when_possible(self):
        names = list("ABCDEFGHIJKL")
        records = self._records(names)
        ranked = rank_pokemon(records)
        rows = beam_search(records, ranked, pool_size=12, beam_width=300)
        selected = select_diverse_candidates(rows, limit=4, min_swaps=2)
        self.assertEqual(len(selected), 4)
        self.assertEqual(selected[0].members, rows[0].members)
        self.assertTrue(
            any(roster_swap_distance(selected[0].members, row.members) >= 2 for row in selected[1:])
        )


if __name__ == "__main__":
    unittest.main()
