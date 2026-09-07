import tempfile
import unittest
from pathlib import Path

from pokequant.ingest import ingest_meta_history, ingest_replay_corpus


class IngestTests(unittest.TestCase):
    def test_meta_history(self):
        with tempfile.TemporaryDirectory() as td:
            def fetcher(target):
                return {"info": {}, "data": {"Great Tusk": {"usage": 0.1}}}

            result = ingest_meta_history(
                Path(td) / "pokequant.db",
                start="2026-07",
                end="2026-08",
                fetcher=fetcher,
            )
            self.assertEqual(result, {"stored": 2, "missing": 0, "failed": 0})

    def test_replay_ingest_dedupes_and_keeps_rating(self):
        with tempfile.TemporaryDirectory() as td:
            def search_iter(**kwargs):
                yield {"id": "gen9ou-1", "rating": 1710}
                yield {"id": "gen9ou-1", "rating": 1710}
                yield {"id": "gen9ou-2", "rating": 1500}

            def replay_fetcher(replay_id):
                return {
                    "id": replay_id,
                    "format": "gen9ou",
                    "uploadtime": 1,
                    "log": "\n".join(
                        [
                            "|player|p1|Alice|",
                            "|player|p2|Bob|",
                            "|poke|p1|Great Tusk, L100|",
                            "|poke|p2|Dragapult, L100|",
                            "|win|Alice",
                        ]
                    ),
                }

            result = ingest_replay_corpus(
                Path(td) / "pokequant.db",
                search_iter=search_iter,
                replay_fetcher=replay_fetcher,
            )
            self.assertEqual(result["inserted"], 2)
            self.assertEqual(result["duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
