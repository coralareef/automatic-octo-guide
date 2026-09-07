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


if __name__ == "__main__":
    unittest.main()
