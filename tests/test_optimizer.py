import unittest

from pokequant.analysis.meta import rank_pokemon
from pokequant.models import PokemonMeta
from pokequant.optimizer.team import beam_search


class OptimizerTests(unittest.TestCase):
    def test_returns_six_unique_members(self):
        records = {}
        names = ["A", "B", "C", "D", "E", "F", "G"]
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
        ranked = rank_pokemon(records)
        result = beam_search(records, ranked, pool_size=7, beam_width=30)
        self.assertTrue(result)
        self.assertEqual(len(result[0].members), 6)
        self.assertEqual(len(set(result[0].members)), 6)


if __name__ == "__main__":
    unittest.main()
