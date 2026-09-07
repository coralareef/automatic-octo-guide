import tempfile
import unittest
from pathlib import Path

from pokequant.analysis.empirical import (
    matchup_matrix,
    pair_synergies,
    pokemon_outcomes,
    wilson_interval,
)
from pokequant.models import ReplaySummary
from pokequant.storage import connect, store_replay


class EmpiricalTests(unittest.TestCase):
    def _seed(self, conn):
        battles = [
            ("b1", 1800, "p1", {"p1": {"A", "B"}, "p2": {"C", "D"}}),
            ("b2", 1750, "p1", {"p1": {"A", "B"}, "p2": {"C", "E"}}),
            ("b3", 1700, "p2", {"p1": {"A", "F"}, "p2": {"C", "D"}}),
            ("b4", 1200, "p2", {"p1": {"A", "B"}, "p2": {"C", "D"}}),
        ]
        for battle_id, rating, winner_side, teams in battles:
            players = (f"{battle_id}-p1", f"{battle_id}-p2")
            winner = players[0] if winner_side == "p1" else players[1]
            replay = ReplaySummary(
                battle_id=battle_id,
                format="gen9ou",
                upload_time=1,
                players=players,
                winner=winner,
                turns=10,
                teams=teams,
            )
            store_replay(conn, replay, "source", rating=rating)

    def test_high_ladder_outcomes_and_synergy(self):
        with tempfile.TemporaryDirectory() as td:
            conn = connect(Path(td) / "x.db")
            self._seed(conn)
            outcomes = {
                row.name: row
                for row in pokemon_outcomes(
                    conn,
                    format="gen9ou",
                    min_rating=1600,
                    prior_strength=0,
                )
            }
            self.assertEqual(outcomes["B"].appearances, 2)
            self.assertEqual(outcomes["B"].wins, 2)
            self.assertLessEqual(outcomes["B"].ci_low, 1.0)

            pairs = {
                (row.a, row.b): row
                for row in pair_synergies(
                    conn,
                    format="gen9ou",
                    min_rating=1600,
                    min_pair_appearances=2,
                    pmi_shrinkage=0,
                    win_prior_strength=0,
                )
            }
            self.assertIn(("A", "B"), pairs)
            self.assertGreater(pairs[("A", "B")].raw_lift, 1.0)
            self.assertEqual(pairs[("A", "B")].pair_decisive_games, 2)
            self.assertEqual(
                pairs[("A", "B")].pair_posterior_win_rate,
                1.0,
            )
            conn.close()

    def test_directional_matchups(self):
        with tempfile.TemporaryDirectory() as td:
            conn = connect(Path(td) / "x.db")
            self._seed(conn)
            rows = matchup_matrix(
                conn,
                format="gen9ou",
                min_rating=1600,
                min_observations=2,
                prior_strength=0,
            )
            matrix = {(row.attacker, row.defender): row for row in rows}
            self.assertGreater(matrix[("A", "C")].posterior_win_rate, 0.5)
            self.assertLess(matrix[("C", "A")].posterior_win_rate, 0.5)
            self.assertEqual(matrix[("A", "C")].observations, 3)
            conn.close()

    def test_wilson_interval_is_bounded(self):
        low, high = wilson_interval(7, 10)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 1.0)
        self.assertLess(low, 0.7)
        self.assertGreater(high, 0.7)


if __name__ == "__main__":
    unittest.main()
