import argparse
import json
from pathlib import Path

from pokequant.analysis.historical import weighted_usage
from pokequant.analysis.meta import parse_chaos, rank_pokemon
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


def cmd_optimize(args: argparse.Namespace) -> int:
    records = parse_chaos(get_chaos(_target(args)))
    ranked = rank_pokemon(records)
    teams = beam_search(
        records,
        ranked,
        pool_size=args.pool,
        beam_width=args.beam,
        team_size=6,
    )[: args.top]
    for idx, team in enumerate(teams, start=1):
        print(f"#{idx} score={team.score:.2f}")
        print("  " + " / ".join(team.members))
        print(
            f"  usage={team.usage_score:.3f} synergy={team.synergy_score:.3f} "
            f"diversity={team.diversity_score:.3f}"
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


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--month", default="2026-08")
    parser.add_argument("--format", default="gen9ou")
    parser.add_argument("--rating", default=1825, type=int)


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

    p_opt = sub.add_parser(
        "optimize", help="Beam-search candidate six-Pokémon teams"
    )
    _add_target_args(p_opt)
    p_opt.add_argument("--pool", type=int, default=40)
    p_opt.add_argument("--beam", type=int, default=250)
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

    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
