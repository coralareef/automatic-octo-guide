import unittest
from unittest.mock import patch

from pokequant.clients.showdown import iter_replays


class ShowdownClientTests(unittest.TestCase):
    def test_paginates_with_51st_result_cursor_and_deduplicates(self):
        first = [
            {"id": f"battle-{i}", "uploadtime": 2000 - i}
            for i in range(51)
        ]
        second = [
            {"id": "battle-50", "uploadtime": 1950},
            {"id": "battle-51", "uploadtime": 1949},
        ]

        with patch(
            "pokequant.clients.showdown.search_replays",
            side_effect=[first, second],
        ) as search:
            rows = list(iter_replays(format="gen9ou", limit=None))

        self.assertEqual(len(rows), 52)
        self.assertEqual(len({row["id"] for row in rows}), 52)
        self.assertIsNone(search.call_args_list[0].kwargs["before"])
        self.assertEqual(search.call_args_list[1].kwargs["before"], 1950)


if __name__ == "__main__":
    unittest.main()
