import unittest

from pokequant.analysis.threats import (
    counter_evidence,
    rank_counter_answers,
    team_threat_coverage,
)
from pokequant.models import PokemonMeta


class ThreatCoverageTests(unittest.TestCase):
    def setUp(self):
        self.records = {
            "ThreatA": PokemonMeta(
                name="ThreatA",
                usage=0.60,
                checks_counters={
                    "AnswerB": {"n": 100.0, "p": 0.80, "d": 0.04},
                    "AnswerC": {"n": 50.0, "p": 0.70, "d": 0.06},
                },
            ),
            "ThreatD": PokemonMeta(
                name="ThreatD",
                usage=0.40,
                checks_counters={
                    "AnswerB": {"n": 40.0, "p": 0.40, "d": 0.08},
                    "AnswerC": {"n": 100.0, "p": 0.90, "d": 0.03},
                },
            ),
            "AnswerB": PokemonMeta(name="AnswerB", usage=0.10),
            "AnswerC": PokemonMeta(name="AnswerC", usage=0.10),
            "Unknown": PokemonMeta(name="Unknown", usage=0.05),
        }

    def test_counter_evidence_shrinks_and_penalizes_uncertainty(self):
        ev = counter_evidence(self.records["ThreatA"], "AnswerB", prior_strength=20, z=1)
        self.assertIsNotNone(ev)
        assert ev is not None
        self.assertGreater(ev.posterior_probability, 0.5)
        self.assertLess(ev.posterior_probability, 0.8)
        self.assertLess(ev.robust_probability, ev.posterior_probability)
        self.assertGreater(ev.robust_probability, 0.6)
        self.assertIsNone(counter_evidence(self.records["ThreatA"], "Unknown"))

    def test_redundant_team_improves_coverage(self):
        solo = team_threat_coverage(
            ["AnswerB"], self.records, top_n=2, prior_strength=20, z=1
        )
        pair = team_threat_coverage(
            ["AnswerB", "AnswerC"], self.records, top_n=2, prior_strength=20, z=1
        )
        self.assertGreater(pair.score, solo.score)
        self.assertLess(pair.uncovered_usage_mass, solo.uncovered_usage_mass)

    def test_answer_ranking_rewards_broad_counter_coverage(self):
        rows = rank_counter_answers(
            self.records, top_n_threats=2, prior_strength=20, z=1
        )
        by_name = {row.answer: row for row in rows}
        self.assertGreater(by_name["AnswerC"].score, by_name["Unknown"].score)
        self.assertGreater(by_name["AnswerB"].score, by_name["Unknown"].score)
        self.assertGreater(by_name["AnswerC"].strong_matchups, 0)


if __name__ == "__main__":
    unittest.main()
