import unittest

from pokequant.parsers.replay import parse_replay


class ReplayParserTests(unittest.TestCase):
    def test_parses_players_team_turns_and_winner(self):
        payload = {
            "id": "gen9ou-test",
            "format": "gen9ou",
            "uploadtime": 123,
            "log": "\n".join(
                [
                    "|player|p1|Arif|1|1500",
                    "|player|p2|Tia|2|1500",
                    "|poke|p1|Great Tusk, M|",
                    "|poke|p2|Dragapult, F|",
                    "|switch|p1a: Tusk|Great Tusk, L100, M|100/100",
                    "|turn|1",
                    "|turn|12",
                    "|win|Arif",
                ]
            ),
        }
        result = parse_replay(payload)
        self.assertEqual(result.players, ("Arif", "Tia"))
        self.assertEqual(result.winner, "Arif")
        self.assertEqual(result.turns, 12)
        self.assertEqual(result.teams["p1"], {"Great Tusk"})
        self.assertEqual(result.teams["p2"], {"Dragapult"})

    def test_partial_log_and_transform_do_not_invent_team_members(self):
        payload = {
            "id": "gen9ou-partial",
            "format": "gen9ou",
            "log": "\n".join(
                [
                    "|player|p1|Alice|",
                    "|poke|p1|Ditto, L100|",
                    "|switch|p1a: Ditto|Ditto, L100|100/100",
                    "|detailschange|p1a: Ditto|Great Tusk, L100|",
                    "|turn|not-a-number",
                ]
            ),
        }
        result = parse_replay(payload)
        self.assertEqual(result.players, ("Alice",))
        self.assertEqual(result.teams["p1"], {"Ditto"})
        self.assertEqual(result.teams["p2"], set())
        self.assertEqual(result.turns, 0)
        self.assertIsNone(result.winner)


if __name__ == "__main__":
    unittest.main()
