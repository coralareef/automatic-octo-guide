import unittest

from pokequant.analysis.stress import CURRENT_OU_STRESS_ROSTERS, stress_archetypes


class StressRosterTests(unittest.TestCase):
    def test_current_suite_spans_distinct_styles(self):
        styles = {row.style for row in CURRENT_OU_STRESS_ROSTERS}
        self.assertEqual(len(CURRENT_OU_STRESS_ROSTERS), 7)
        self.assertEqual(len(styles), 7)
        self.assertTrue(all(len(row.members) == 6 for row in CURRENT_OU_STRESS_ROSTERS))
        self.assertTrue(all(len(set(row.members)) == 6 for row in CURRENT_OU_STRESS_ROSTERS))

    def test_stress_archetypes_are_equal_weight_and_normalized(self):
        rows = stress_archetypes()
        self.assertEqual(len(rows), len(CURRENT_OU_STRESS_ROSTERS))
        self.assertAlmostEqual(sum(row.proposal_probability for row in rows), 1.0, places=8)
        self.assertTrue(all(abs(row.proposal_probability - 1 / 7) < 1e-12 for row in rows))


if __name__ == "__main__":
    unittest.main()
