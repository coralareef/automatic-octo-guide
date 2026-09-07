import math
import unittest

from pokequant.history import month_range, time_decay_weight


class HistoryTests(unittest.TestCase):
    def test_month_range_and_decay(self):
        self.assertEqual(
            month_range("2026-06", "2026-08"),
            ["2026-06", "2026-07", "2026-08"],
        )
        self.assertTrue(
            math.isclose(
                time_decay_weight("2026-05", "2026-08", 3.0),
                0.5,
            )
        )


if __name__ == "__main__":
    unittest.main()
