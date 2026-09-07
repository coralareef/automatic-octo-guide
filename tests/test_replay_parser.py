import unittest

from pokequant.parsers.replay import parse_replay


class ReplayParserTests(unittest.TestCase):
    def test_parses_players_team_turns_winner_and_ratings(self):
        payload = {
            "id": "gen9ou-test",
            "format": "[Gen 9] OU",
            "formatid": "gen9ou",
            "uploadtime": 123,
            "log": "\n".join(
                [
                    "|player|p1|Arif|1|1500",
                    "|player|p2|Tia|2|1600",
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
        self.assertEqual(result.format, "gen9ou")
        self.assertEqual(result.players, ("Arif", "Tia"))
        self.assertEqual(result.player_ratings, (1500, 1600))
        self.assertEqual(result.rating, 1500)
        self.assertEqual(result.winner, "Arif")
        self.assertEqual(result.turns, 12)
        self.assertEqual(result.teams["p1"], {"Great Tusk"})
        self.assertEqual(result.teams["p2"], {"Dragapult"})

    def test_payload_players_fill_redacted_log_names(self):
        payload = {
            "id": "gen9ou-private-names",
            "formatid": "gen9ou",
            "players": ["Alice", "Bob"],
            "rating": 1700,
            "log": "\n".join(
                [
                    "|player|p1||1|1710",
                    "|player|p2||2|1690",
                    "|poke|p1|Great Tusk, L100|",
                    "|poke|p2|Dragapult, L100|",
                    "|win|Bob",
                ]
            ),
        }
        result = parse_replay(payload)
        self.assertEqual(result.players, ("Alice", "Bob"))
        self.assertEqual(result.rating, 1700)
        self.assertEqual(result.player_ratings, (1710, 1690))

    def test_partial_log_and_transform_do_not_invent_team_members(self):
        payload = {
            "id": "gen9ou-partial",
            "formatid": "gen9ou",
            "players": ["Alice"],
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
        self.assertEqual(result.players, ("Alice", ""))
        self.assertEqual(result.teams["p1"], {"Ditto"})
        self.assertEqual(result.teams["p2"], set())
        self.assertEqual(result.turns, 0)
        self.assertIsNone(result.winner)


if __name__ == "__main__":
    unittest.main()
