import unittest

from pokequant.evaluation import (
    OpponentTeam,
    deterministic_seed,
    evaluate_candidate,
    evaluate_candidate_batched,
)
from pokequant.simulator import SimulationResult


def result(winner: str, *, errors: int = 0, seed: str = "1,2,3,4") -> SimulationResult:
    return SimulationResult(
        format="gen9ou",
        winner=winner,
        turns=10,
        requests=20,
        seed=seed,
        policy="fake",
        errors=errors,
    )


class EvaluationTests(unittest.TestCase):
    def test_side_pairing_cancels_p1_bias(self):
        def always_p1(*args, **kwargs):
            return result("P1")

        evaluated = evaluate_candidate(
            "candidate",
            [OpponentTeam("meta", "opponent", 1.0)],
            simulator=always_p1,
            seeds_per_opponent=5,
        )
        self.assertAlmostEqual(evaluated.expected_win, 0.5)
        self.assertEqual(evaluated.total_battles, 10)
        self.assertEqual(evaluated.protocol_errors, 0)

    def test_weighted_population_and_downside_risk(self):
        def matchup_sim(p1team, p2team, **kwargs):
            opponent = p2team if p1team == "candidate" else p1team
            candidate_is_p1 = p1team == "candidate"
            candidate_wins = opponent == "easy"
            if candidate_wins:
                return result("P1" if candidate_is_p1 else "P2")
            return result("P2" if candidate_is_p1 else "P1")

        evaluated = evaluate_candidate(
            "candidate",
            [
                OpponentTeam("easy", "easy", 0.75),
                OpponentTeam("hard", "hard", 0.25),
            ],
            simulator=matchup_sim,
            seeds_per_opponent=2,
            risk_lambda=0.5,
        )
        self.assertAlmostEqual(evaluated.expected_win, 0.75)
        self.assertAlmostEqual(evaluated.matchups[0].win_rate, 0.0)
        self.assertAlmostEqual(evaluated.matchups[1].win_rate, 1.0)
        self.assertLess(evaluated.downside_cvar, evaluated.expected_win)
        self.assertGreater(evaluated.risk, 0)
        self.assertLess(evaluated.objective, evaluated.expected_win)

    def test_batched_matches_scalar_estimator(self):
        opponents = [
            OpponentTeam("easy", "easy", 0.7),
            OpponentTeam("hard", "hard", 0.3),
        ]

        def matchup_sim(p1team, p2team, **kwargs):
            opponent = p2team if p1team == "candidate" else p1team
            candidate_is_p1 = p1team == "candidate"
            candidate_wins = opponent == "easy"
            winner = ("P1" if candidate_is_p1 else "P2") if candidate_wins else (
                "P2" if candidate_is_p1 else "P1"
            )
            return result(winner, seed=kwargs.get("seed", "1,2,3,4"))

        def batch_sim(cases, **kwargs):
            return tuple(
                matchup_sim(case.p1team, case.p2team, seed=case.seed)
                for case in cases
            )

        scalar = evaluate_candidate(
            "candidate",
            opponents,
            simulator=matchup_sim,
            seeds_per_opponent=3,
            base_seed=99,
            risk_lambda=0.25,
        )
        batched = evaluate_candidate_batched(
            "candidate",
            opponents,
            batch_simulator=batch_sim,
            seeds_per_opponent=3,
            base_seed=99,
            risk_lambda=0.25,
        )
        self.assertAlmostEqual(scalar.expected_win, batched.expected_win)
        self.assertAlmostEqual(scalar.objective, batched.objective)
        self.assertAlmostEqual(scalar.downside_cvar, batched.downside_cvar)
        self.assertEqual(scalar.total_battles, batched.total_battles)
        self.assertEqual(scalar.matchups, batched.matchups)

    def test_seed_is_reproducible_and_opponent_specific(self):
        self.assertEqual(
            deterministic_seed(42, "A", 1), deterministic_seed(42, "A", 1)
        )
        self.assertNotEqual(
            deterministic_seed(42, "A", 1), deterministic_seed(42, "B", 1)
        )

    def test_strict_protocol_rejects_choice_errors(self):
        def bad_sim(*args, **kwargs):
            return result("P1", errors=1)

        with self.assertRaises(RuntimeError):
            evaluate_candidate(
                "candidate",
                [OpponentTeam("meta", "opponent", 1.0)],
                simulator=bad_sim,
                seeds_per_opponent=1,
            )

    def test_batched_strict_protocol_rejects_choice_errors(self):
        def bad_batch(cases, **kwargs):
            return tuple(result("P1", errors=1, seed=case.seed) for case in cases)

        with self.assertRaises(RuntimeError):
            evaluate_candidate_batched(
                "candidate",
                [OpponentTeam("meta", "opponent", 1.0)],
                batch_simulator=bad_batch,
                seeds_per_opponent=1,
            )


if __name__ == "__main__":
    unittest.main()
