import tempfile
import unittest
from pathlib import Path

from pokequant.config import MetaTarget
from pokequant.models import ReplaySummary
from pokequant.storage import connect, corpus_stats, store_meta_snapshot, store_replay


class StorageTests(unittest.TestCase):
    def test_storage_deduplicates_and_replaces_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            conn = connect(Path(td) / "pokequant.db")
            target = MetaTarget(month="2026-08", format="gen9ou", rating=1825)
            payload = {
                "info": {"battles": 100},
                "data": {
                    "Great Tusk": {
                        "usage": 0.2,
                        "Raw count": 10,
                        "Moves": {"Earthquake": 10},
                    }
                },
            }
            store_meta_snapshot(conn, target, payload)
            store_meta_snapshot(conn, target, payload)

            replay = ReplaySummary(
                battle_id="gen9ou-test",
                format="gen9ou",
                upload_time=1,
                players=("Arif", "Tia"),
                winner="Arif",
                turns=4,
                teams={"p1": {"Great Tusk"}, "p2": {"Dragapult"}},
            )
            self.assertTrue(store_replay(conn, replay, "source", rating=1700))
            self.assertFalse(store_replay(conn, replay, "source", rating=1700))
            self.assertEqual(
                corpus_stats(conn),
                {
                    "meta_snapshots": 1,
                    "pokemon_rows": 1,
                    "replays": 1,
                    "team_members": 2,
                },
            )
            stored = conn.execute(
                "SELECT rating, winner_side FROM replays WHERE battle_id=?",
                ("gen9ou-test",),
            ).fetchone()
            self.assertEqual(stored["rating"], 1700)
            self.assertEqual(stored["winner_side"], "p1")
            conn.close()


if __name__ == "__main__":
    unittest.main()
