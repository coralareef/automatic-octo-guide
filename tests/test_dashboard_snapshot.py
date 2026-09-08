import json
import unittest
from pathlib import Path


class DashboardSnapshotTests(unittest.TestCase):
    def test_latest_snapshot_has_auditable_research_state(self):
        path = Path(__file__).resolve().parents[1] / "dashboard" / "latest_snapshot.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        evidence = payload["evidence"]
        leader = payload["leading_candidate"]

        self.assertGreaterEqual(evidence["historical_snapshots"], 24)
        self.assertGreater(evidence["pokemon_rows"], 0)
        self.assertEqual(len(leader["members"]), 6)
        self.assertEqual(len(set(leader["members"])), 6)
        self.assertGreaterEqual(leader["ci_low"], 0.0)
        self.assertLessEqual(leader["ci_high"], 1.0)
        self.assertLessEqual(leader["ci_low"], leader["expected_win"])
        self.assertGreaterEqual(leader["ci_high"], leader["expected_win"])
        self.assertIn("not final", leader["status"])

        gates = {row["gate"]: row["status"] for row in payload["research_gates"]}
        self.assertEqual(gates["Large Monte Carlo sample"], "not yet")
        self.assertEqual(gates["Out-of-sample future-month backtest"], "not yet")


if __name__ == "__main__":
    unittest.main()
