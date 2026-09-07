import argparse
import json
from pathlib import Path

from pokequant.analysis.empirical import matchup_matrix, pair_synergies, pokemon_outcomes
from pokequant.analysis.historical import weighted_usage
from pokequant.analysis.meta import parse_chaos, rank_pokemon
from pokequant.analysis.threats import rank_counter_answers, team_threat_coverage
from pokequant.clients.showdown import get_replay, iter_replays
from pokequant.clients.smogon import get_chaos
from pokequant.config import MetaTarget
from pokequant.ingest import ingest_meta_history, ingest_replay_corpus
from pokequant.optimizer.team import beam_search
from pokequant.parsers.replay import parse_replay
from pokequant.storage import connect, corpus_stats


def _target(args: argparse.Namespace) -> MetaTarget:
    return MetaTarget(month=args.month, format=args.format, rating=args.rating)


def cmd_meta(args: argparse.Namespace) -> int:
    target = _target(args)
    payload = get_chaos(target)
    records = parse_chaos(payload)
    print(f"source={target.chaos_url}")
    print(f"pokemon={len(records)}")
    print(f"info={json.dumps(payload.get('info', {}), ensure_ascii=False)}")
    return 0


def cmd_replays(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for stub in iter_replays(user=args.user, format=args.format, limit=args.limit):
        battle_id = str(stub["id"])
        payload = get_replay(battle_id)
        summary = parse_replay(payload)
        row = {
            "id": summary.battle_id,
            "format": summary.format,
            "uploadtime": summary.upload_time,
            "players": summary.players,
            "winner": summary.winner,
            "turns": summary.turns,
            "teams": {k: sorted(v) for k, v in summary.teams.items()},
        }
        (out_dir / f"{battle_id}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        count += 1
    print(f"saved={count} directory={out_dir}")
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    payload = get_chaos(_target(args))
    ranked = rank_pokemon(parse_chaos(payload))[: args.top]
    print("rank\tpokemon\tscore\tusage\tversatility")
    for idx, mon in enumerate(ranked, start=1):
        print(
            f"{idx}\t{mon.name}\t{mon.score:.2f}\t"
            f"{mon.usage:.6g}\t{mon.versatility:.3f}"
        )
    return 0


def cmd_threat_answers(args: argparse.Namespace) -> int:
    records = parse_chaos(get_chaos(_target(args)))
    rows = rank_counter_answers(
        records,
        top_n_threats=args.threats,
        prior_strength=args.prior,
        z=args.z,
        strong_threshold=args.strong_threshold,
    )[: args.top]
    print("rank\tpokemon\tcoverage_score\tstrong_usage_mass\tstrong_matchups")
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}\t{row.answer}\t{row.score:.4f}\t"
            f"{row.covered_usage_mass:.4f}\t{row.strong_matchups}"
        )
    return 0


def cmd_threat_coverage(args: argparse.Namespace) -> int:
    records = parse_chaos(get_chaos(_target(args)))
    members = tuple(part.strip() for part in args.team.split(",") if part.strip())
    unknown = [name for name in members if name not in records]
    if unknown:
        print("unknown=" + ",".join(unknown))
        return 2
    result = team_threat_coverage(
        members,
        records,
        top_n=args.threats,
        prior_strength=args.prior,
        z=args.z,
        redundancy_weight=args.redundancy,
        uncovered_threshold=args.uncovered_threshold,
    )
    print(
        f"team={' / '.join(result.members)}\tcoverage={result.score:.4f}\t"
        f"uncovered_usage_mass={result.uncovered_usage_mass:.4f}"
    )
    print("threat\tusage\tbest_answer\tbest\tsecond_answer\tsecond\tcombined")
    for row in result.threats[: args.show]:
        print(
            f"{row.threat}\t{row.usage:.6g}\t{row.best_answer or '-'}\t"
            f"{row.best_score:.4f}\t{row.second_answer or '-'}\t"
            f"{row.second_score:.4f}\t{row.combined_score:.4f}"
        )
    return 0


def cmd_optimize(args: argparse.Namespace) -> int:
    records = parse_chaos(get_chaos(_target(args)))
    ranked = rank_pokemon(records)
    teams = beam_search(
        records,
        ranked,
        pool_size=args.pool,
        beam_width=args.beam,
        team_size=6,
        threat_top_n=args.threats,
    )[: args.top]
    for idx, team in enumerate(teams, start=1):
        print(f"#{idx} score={team.score:.2f}")
        print("  " + " / ".join(team.members))
        print(
            f"  usage={team.usage_score:.3f} synergy={team.synergy_score:.3f} "
            f"diversity={team.diversity_score:.3f} threat={team.threat_score:.3f}"
        )
    return 0


def cmd_warehouse_meta(args: argparse.Namespace) -> int:
    result = ingest_meta_history(
        args.db,
        start=args.start,
        end=args.end,
        format=args.format,
        rating=args.rating,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 2


def cmd_warehouse_replays(args: argparse.Namespace) -> int:
    limit = None if args.limit == 0 else args.limit
    result = ingest_replay_corpus(
        args.db,
        user=args.user,
        user2=args.user2,
        format=args.format,
        limit=limit,
        sleep_seconds=args.sleep,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["failed"] == 0 else 2


def cmd_warehouse_stats(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    try:
        print(json.dumps(corpus_stats(conn), sort_keys=True))
    finally:
        conn.close()
    return 0


def cmd_historical_rank(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    try:
        rows = weighted_usage(
            conn,
            format=args.format,
            rating=args.rating,
            reference_month=args.reference,
            half_life_months=args.half_life,
        )[: args.top]
    finally:
        conn.close()

    print("rank\tpokemon\tweighted_usage\tsnapshots\teffective_weight")
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}\t{row.name}\t{row.weighted_usage:.8g}\t"
            f"{row.snapshots}\t{row.effective_weight:.3f}"
        )
    return 0


def cmd_empirical_pokemon(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    try:
        rows = pokemon_outcomes(
            conn,
            format=args.format,
            min_rating=args.min_rating,
            prior_strength=args.prior,
        )[: args.top]
    finally:
        conn.close()
    print("rank\tpokemon\tgames\twins\tposterior_win\tci_low\tci_high")
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}\t{row.name}\t{row.appearances}\t{row.wins}\t"
            f"{row.posterior_win_rate:.4f}\t{row.ci_low:.4f}\t{row.ci_high:.4f}"
        )
    return 0


def cmd_empirical_pairs(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    try:
        rows = pair_synergies(
            conn,
            format=args.format,
            min_rating=args.min_rating,
            min_pair_appearances=args.min_games,
            pmi_shrinkage=args.shrinkage,
            win_prior_strength=args.prior,
        )[: args.top]
    finally:
        conn.close()
    print(
        "rank\tpair\tteam_games\tlift\tshrunk_pmi\tpair_win\tci_low\tci_high"
    )
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}\t{row.a} + {row.b}\t{row.team_appearances}\t"
            f"{row.raw_lift:.3f}\t{row.shrunk_pmi:.4f}\t"
            f"{row.pair_posterior_win_rate:.4f}\t"
            f"{row.pair_ci_low:.4f}\t{row.pair_ci_high:.4f}"
        )
    return 0


def cmd_empirical_matchups(args: argparse.Namespace) -> int:
    conn = connect(args.db)
    try:
        rows = matchup_matrix(
            conn,
            format=args.format,
            min_rating=args.min_rating,
            min_observations=args.min_games,
            prior_strength=args.prior,
        )
    finally:
        conn.close()
    if args.pokemon:
        key = args.pokemon.casefold()
        rows = [
            row
            for row in rows
            if row.attacker.casefold() == key or row.defender.casefold() == key
        ]
    rows = rows[: args.top]
    print("rank\tattacker\tdefender\tgames\tposterior_win\tci_low\tci_high")
    for idx, row in enumerate(rows, start=1):
        print(
            f"{idx}\t{row.attacker}\t{row.defender}\t{row.observations}\t"
            f"{row.posterior_win_rate:.4f}\t{row.ci_low:.4f}\t{row.ci_high:.4f}"
        )
    return 0


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--month", default="2026-08")
    parser.add_argument("--format", default="gen9ou")
    parser.add_argument("--rating", default=1825, type=int)


def _add_threat_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--threats", type=int, default=30)
    parser.add_argument("--prior", type=float, default=20.0)
    parser.add_argument("--z", type=float, default=1.0)


def _add_empirical_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default="data/pokequant.db")
    parser.add_argument("--format", default="gen9ou")
    parser.add_argument("--min-rating", type=int, default=1600)
    parser.add_argument("--prior", type=float, default=12.0)
    parser.add_argument("--top", type=int, default=30)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pokequant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_meta = sub.add_parser("meta", help="Download and summarize Smogon chaos data")
    _add_target_args(p_meta)
    p_meta.set_defaults(func=cmd_meta)

    p_replays = sub.add_parser("replays", help="Download public Showdown replays")
    p_replays.add_argument("--user")
    p_replays.add_argument("--format", default="gen9ou")
    p_replays.add_argument("--limit", type=int, default=100)
    p_replays.add_argument("--out", default="data/replays")
    p_replays.set_defaults(func=cmd_replays)

    p_rank = sub.add_parser("rank", help="Rank Pokémon from a target meta")
    _add_target_args(p_rank)
    p_rank.add_argument("--top", type=int, default=30)
    p_rank.set_defaults(func=cmd_rank)

    p_answers = sub.add_parser(
        "threat-answers",
        help="Rank Pokémon by confidence-adjusted coverage of top meta threats",
    )
    _add_target_args(p_answers)
    _add_threat_args(p_answers)
    p_answers.add_argument("--strong-threshold", type=float, default=0.60)
    p_answers.add_argument("--top", type=int, default=30)
    p_answers.set_defaults(func=cmd_threat_answers)

    p_coverage = sub.add_parser(
        "threat-coverage",
        help="Score a comma-separated team against top meta threats",
    )
    _add_target_args(p_coverage)
    _add_threat_args(p_coverage)
    p_coverage.add_argument("--team", required=True)
    p_coverage.add_argument("--redundancy", type=float, default=0.25)
    p_coverage.add_argument("--uncovered-threshold", type=float, default=0.55)
    p_coverage.add_argument("--show", type=int, default=30)
    p_coverage.set_defaults(func=cmd_threat_coverage)

    p_opt = sub.add_parser(
        "optimize", help="Beam-search candidate six-Pokémon teams"
    )
    _add_target_args(p_opt)
    p_opt.add_argument("--pool", type=int, default=40)
    p_opt.add_argument("--beam", type=int, default=250)
    p_opt.add_argument("--threats", type=int, default=30)
    p_opt.add_argument("--top", type=int, default=10)
    p_opt.set_defaults(func=cmd_optimize)

    p_wh_meta = sub.add_parser(
        "warehouse-meta", help="Ingest monthly Smogon snapshots into SQLite"
    )
    p_wh_meta.add_argument("--db", default="data/pokequant.db")
    p_wh_meta.add_argument("--start", default="2023-01")
    p_wh_meta.add_argument("--end", default="2026-08")
    p_wh_meta.add_argument("--format", default="gen9ou")
    p_wh_meta.add_argument("--rating", type=int, default=1825)
    p_wh_meta.set_defaults(func=cmd_warehouse_meta)

    p_wh_replays = sub.add_parser(
        "warehouse-replays",
        help="Ingest discoverable public Showdown replays into SQLite",
    )
    p_wh_replays.add_argument("--db", default="data/pokequant.db")
    p_wh_replays.add_argument("--user")
    p_wh_replays.add_argument("--user2")
    p_wh_replays.add_argument("--format", default="gen9ou")
    p_wh_replays.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="0 means paginate until the API has no more results",
    )
    p_wh_replays.add_argument("--sleep", type=float, default=0.05)
    p_wh_replays.set_defaults(func=cmd_warehouse_replays)

    p_wh_stats = sub.add_parser(
        "warehouse-stats", help="Show warehouse row counts"
    )
    p_wh_stats.add_argument("--db", default="data/pokequant.db")
    p_wh_stats.set_defaults(func=cmd_warehouse_stats)

    p_hist = sub.add_parser(
        "historical-rank", help="Rank Pokémon by time-decayed historical usage"
    )
    p_hist.add_argument("--db", default="data/pokequant.db")
    p_hist.add_argument("--format", default="gen9ou")
    p_hist.add_argument("--rating", type=int, default=1825)
    p_hist.add_argument("--reference", default="2026-08")
    p_hist.add_argument("--half-life", type=float, default=3.0)
    p_hist.add_argument("--top", type=int, default=30)
    p_hist.set_defaults(func=cmd_historical_rank)

    p_ep = sub.add_parser(
        "empirical-pokemon",
        help="Rank Pokémon by shrinkage-adjusted replay win rate",
    )
    _add_empirical_args(p_ep)
    p_ep.set_defaults(func=cmd_empirical_pokemon)

    p_pairs = sub.add_parser(
        "empirical-pairs",
        help="Rank teammate pairs by lift/PMI and observed outcomes",
    )
    _add_empirical_args(p_pairs)
    p_pairs.add_argument("--min-games", type=int, default=10)
    p_pairs.add_argument("--shrinkage", type=float, default=8.0)
    p_pairs.set_defaults(func=cmd_empirical_pairs)

    p_match = sub.add_parser(
        "empirical-matchups",
        help="Estimate directional Pokémon-vs-Pokémon matchup outcomes",
    )
    _add_empirical_args(p_match)
    p_match.add_argument("--min-games", type=int, default=10)
    p_match.add_argument("--pokemon")
    p_match.set_defaults(func=cmd_empirical_matchups)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
