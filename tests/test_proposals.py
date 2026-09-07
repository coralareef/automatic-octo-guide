import unittest
from dataclasses import dataclass

from pokequant.analysis.population import OpponentArchetype
from pokequant.models import PokemonMeta
from pokequant.proposals import build_legal_opponent_proposals


@dataclass
class FakeValidation:
    valid: bool
    export: str


class ProposalTests(unittest.TestCase):
    def _records(self):
        names = list("ABCDEFG")
        records = {}
        for name in names:
            records[name] = PokemonMeta(
                name=name,
                usage=0.1,
                items={"leftovers": 100},
                abilities={"pressure": 100},
                tera_types={"water": 100},
                spreads={"Serious:4/0/0/0/0/0": 100},
                moves={"tackle": 100, "protect": 80, "rest": 60, "toxic": 40},
            )
        return records

    def test_builds_and_normalizes_legal_variants(self):
        records = self._records()
        archetypes = [
            OpponentArchetype(("A", "B", "C", "D", "E", "F"), 1, 0.7, 0, 0),
            OpponentArchetype(("A", "B", "C", "D", "E", "G"), 1, 0.3, 0, 0),
        ]

        def validator(team, *, format):
            return FakeValidation(True, team)

        rows, stats = build_legal_opponent_proposals(
            archetypes,
            records,
            validator=validator,
            variants_per_archetype=2,
            per_species=2,
            beam_width=8,
            proposal_limit=4,
        )
        self.assertEqual(stats.archetypes_covered, 2)
        self.assertEqual(len(rows), 4)
        self.assertAlmostEqual(sum(row.weight for row in rows), 1.0, places=8)
        first_mass = sum(row.weight for row in rows if row.members[-1] == "F")
        second_mass = sum(row.weight for row in rows if row.members[-1] == "G")
        self.assertAlmostEqual(first_mass, 0.7, places=6)
        self.assertAlmostEqual(second_mass, 0.3, places=6)

    def test_missing_legal_archetype_is_renormalized(self):
        records = self._records()
        archetypes = [
            OpponentArchetype(("A", "B", "C", "D", "E", "F"), 1, 0.8, 0, 0),
            OpponentArchetype(("A", "B", "C", "D", "E", "G"), 1, 0.2, 0, 0),
        ]

        def validator(team, *, format):
            return FakeValidation("G @" not in team, team)

        rows, stats = build_legal_opponent_proposals(
            archetypes,
            records,
            validator=validator,
            variants_per_archetype=1,
            per_species=1,
            beam_width=2,
            proposal_limit=2,
        )
        self.assertEqual(stats.archetypes_covered, 1)
        self.assertTrue(rows)
        self.assertAlmostEqual(sum(row.weight for row in rows), 1.0, places=8)
        self.assertTrue(all(row.members[-1] == "F" for row in rows))


if __name__ == "__main__":
    unittest.main()
