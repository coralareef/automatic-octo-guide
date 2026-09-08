import json
import tempfile
import unittest
from pathlib import Path

from pokequant.analysis.historical import weighted_meta_records
from pokequant.config import MetaTarget
from pokequant.storage import connect, store_meta_snapshot


class HistoricalMetaTests(unittest.TestCase):
    def test_weighted_meta_records_pool_battle_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "history.db"
            conn = connect(db)
            try:
                store_meta_snapshot(
                    conn,
                    MetaTarget(month="2026-07", format="gen9ou", rating=1825),
                    {
                        "data": {
                            "Alpha": {
                                "usage": 0.20,
                                "Raw count": 100,
                                "Moves": {"Move A": 60, "Move B": 40},
                                "Items": {"Item A": 100},
                                "Abilities": {"Ability A": 100},
                                "Tera Types": {"Water": 70, "Steel": 30},
                                "Spreads": {"Timid:0/0/0/252/4/252": 100},
                                "Teammates": {"Beta": 50},
                                "Checks and Counters": {
                                    "Beta": {"n": 20, "p": 0.70, "d": 0.10}
                                },
                            }
                        }
                    },
                )
                store_meta_snapshot(
                    conn,
                    MetaTarget(month="2026-08", format="gen9ou", rating=1825),
                    {
                        "data": {
                            "Alpha": {
                                "usage": 0.40,
                                "Raw count": 200,
                                "Moves": {"Move A": 100, "Move C": 100},
                                "Items": {"Item A": 150, "Item B": 50},
                                "Abilities": {"Ability A": 200},
                                "Tera Types": {"Water": 100, "Fairy": 100},
                                "Spreads": {"Timid:0/0/0/252/4/252": 200},
                                "Teammates": {"Beta": 100},
                                "Checks and Counters": {
                                    "Beta": {"n": 40, "p": 0.50, "d": 0.20}
                                },
                            }
                        }
                    },
                )

                records = weighted_meta_records(
                    conn,
                    format="gen9ou",
                    rating=1825,
                    reference_month="2026-08",
                    half_life_months=1.0,
                )
            finally:
                conn.close()

            alpha = records["Alpha"]
            self.assertAlmostEqual(alpha.usage, (0.20 * 0.5 + 0.40) / 1.5)
            self.assertAlmostEqual(alpha.raw_count, 100 * 0.5 + 200)
            self.assertAlmostEqual(alpha.moves["Move A"], 60 * 0.5 + 100)
            self.assertAlmostEqual(alpha.teammates["Beta"], 50 * 0.5 + 100)
            counter = alpha.checks_counters["Beta"]
            self.assertAlmostEqual(counter["n"], 20 * 0.5 + 40)
            expected_p = ((20 * 0.5) * 0.70 + 40 * 0.50) / (20 * 0.5 + 40)
            self.assertAlmostEqual(counter["p"], expected_p)
            self.assertGreater(counter["d"], 0.0)


if __name__ == "__main__":
    unittest.main()
