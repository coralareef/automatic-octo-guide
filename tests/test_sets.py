import unittest

from pokequant.models import PokemonMeta
from pokequant.sets import (
    Spread,
    build_team_export,
    generate_set_candidates,
    generate_team_set_candidates,
    parse_spread,
    set_coherence,
)


class SetCandidateTests(unittest.TestCase):
    def test_parse_spread(self):
        spread = parse_spread("Jolly:0/252/0/0/4/252")
        self.assertIsNotNone(spread)
        assert spread is not None
        self.assertEqual(spread.nature, "Jolly")
        self.assertEqual(spread.evs, (0, 252, 0, 0, 4, 252))
        self.assertIsNone(parse_spread("broken"))

    def _mon(self, name: str) -> PokemonMeta:
        return PokemonMeta(
            name=name,
            usage=0.2,
            items={"leftovers": 80, "choicescarf": 20},
            abilities={"pressure": 100},
            tera_types={"water": 60, "steel": 40},
            spreads={
                "Jolly:0/252/0/0/4/252": 70,
                "Adamant:0/252/0/0/4/252": 30,
            },
            moves={
                "movea": 100,
                "moveb": 90,
                "movec": 80,
                "moved": 70,
                "movee": 30,
            },
        )

    def test_generates_ranked_four_move_sets(self):
        mon = self._mon("Examplemon")
        rows = generate_set_candidates(mon, limit=10)
        self.assertTrue(rows)
        self.assertEqual(len(rows[0].moves), 4)
        self.assertEqual(rows[0].item, "leftovers")
        self.assertEqual(rows[0].spread.nature, "Jolly")
        self.assertIn("EVs: 252 Atk / 4 SpD / 252 Spe", rows[0].export())
        self.assertIn("- movea", rows[0].export())
        self.assertGreaterEqual(rows[0].marginal_score, rows[-1].marginal_score)

    def test_choice_setup_and_recovery_are_heavily_penalized(self):
        spread = Spread("Timid", (0, 0, 0, 252, 4, 252))
        bad = set_coherence(
            item="Choice Scarf",
            moves=("makeitrain", "shadowball", "recover", "nastyplot"),
            spread=spread,
        )
        good = set_coherence(
            item="Choice Scarf",
            moves=("makeitrain", "shadowball", "focusblast", "trick"),
            spread=spread,
        )
        self.assertLess(bad, 0.1)
        self.assertGreater(good, 0.9)

    def test_body_press_iron_defense_prefers_defense_spread(self):
        offensive = Spread("Jolly", (0, 252, 0, 0, 4, 252))
        defensive = Spread("Impish", (252, 0, 252, 0, 4, 0))
        moves = ("bodypress", "irondefense", "crunch", "substitute")
        self.assertGreater(
            set_coherence(item="Leftovers", moves=moves, spread=defensive),
            set_coherence(item="Leftovers", moves=moves, spread=offensive),
        )

    def test_iron_defense_without_body_press_is_penalized(self):
        offensive = Spread("Jolly", (0, 252, 0, 0, 4, 252))
        incoherent = set_coherence(
            item="Leftovers",
            moves=("irondefense", "closecombat", "crunch", "heavyslam"),
            spread=offensive,
        )
        coherent = set_coherence(
            item="Leftovers",
            moves=("bodypress", "irondefense", "crunch", "substitute"),
            spread=Spread("Impish", (252, 0, 252, 0, 4, 0)),
        )
        self.assertLess(incoherent, 0.1)
        self.assertGreater(coherent, 0.9)

    def test_assault_vest_status_move_is_penalized(self):
        spread = Spread("Timid", (0, 0, 0, 252, 4, 252))
        bad = set_coherence(
            item="Assault Vest",
            moves=("icebeam", "earthpower", "recover", "freezedry"),
            spread=spread,
        )
        self.assertLess(bad, 0.1)

    def test_light_clay_requires_a_screen_move(self):
        spread = Spread("Jolly", (0, 252, 0, 0, 4, 252))
        bad = set_coherence(
            item="Light Clay",
            moves=("closecombat", "crunch", "heavyslam", "icefang"),
            spread=spread,
        )
        good = set_coherence(
            item="Light Clay",
            moves=("reflect", "lightscreen", "closecombat", "crunch"),
            spread=spread,
        )
        self.assertLess(bad, 0.1)
        self.assertGreater(good, 0.9)

    def test_weather_rock_accepts_matching_move_or_ability(self):
        spread = Spread("Timid", (0, 0, 0, 252, 4, 252))
        bad = set_coherence(
            item="Damp Rock",
            ability="Keen Eye",
            moves=("hydropump", "hurricane", "roost", "uturn"),
            spread=spread,
        )
        manual = set_coherence(
            item="Damp Rock",
            ability="Keen Eye",
            moves=("raindance", "hurricane", "roost", "uturn"),
            spread=spread,
        )
        automatic = set_coherence(
            item="Damp Rock",
            ability="Drizzle",
            moves=("hydropump", "hurricane", "roost", "uturn"),
            spread=spread,
        )
        self.assertLess(bad, 0.1)
        self.assertGreater(manual, 0.9)
        self.assertGreater(automatic, 0.9)

    def test_terrain_extender_accepts_surge_ability(self):
        spread = Spread("Jolly", (0, 252, 0, 0, 4, 252))
        good = set_coherence(
            item="Terrain Extender",
            ability="Grassy Surge",
            moves=("woodhammer", "knockoff", "uturn", "grassyglide"),
            spread=spread,
        )
        self.assertGreater(good, 0.9)

    def test_booster_energy_requires_paradox_ability(self):
        spread = Spread("Timid", (0, 0, 0, 252, 4, 252))
        bad = set_coherence(
            item="Booster Energy",
            ability="Pressure",
            moves=("moonblast", "thunderbolt", "focusblast", "shadowball"),
            spread=spread,
        )
        good = set_coherence(
            item="Booster Energy",
            ability="Quark Drive",
            moves=("moonblast", "thunderbolt", "focusblast", "shadowball"),
            spread=spread,
        )
        self.assertLess(bad, 0.1)
        self.assertGreater(good, 0.9)

    def test_team_export_separates_sets(self):
        mon = PokemonMeta(
            name="Examplemon",
            usage=0.2,
            moves={"a": 4, "b": 3, "c": 2, "d": 1},
        )
        candidate = generate_set_candidates(mon, limit=1)[0]
        export = build_team_export([candidate, candidate])
        self.assertIn("\n\n", export)

    def test_beam_generates_ranked_exact_team_variants(self):
        records = {name: self._mon(name) for name in ("A", "B", "C")}
        rows = generate_team_set_candidates(
            ("A", "B", "C"), records, per_species=3, beam_width=8, limit=5
        )
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0].members, ("A", "B", "C"))
        self.assertGreaterEqual(rows[0].marginal_score, rows[-1].marginal_score)
        self.assertEqual(rows[0].export().count("\n\n"), 2)


if __name__ == "__main__":
    unittest.main()
