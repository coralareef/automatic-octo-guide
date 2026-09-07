# Pokémon Quant

A quantitative Pokémon Showdown metagame and team-optimization project.

The objective is to estimate the legal six-Pokémon team that maximizes expected win probability against a target metagame, then explain why each slot was selected.

## Current status

V0.2 adds a reproducible SQLite warehouse for historical Smogon snapshots and public Pokémon Showdown replays. The optimizer is still heuristic until the empirical matchup model and simulator milestones are complete.

Default research target: **Gen 9 OU, August 2026, 1825-weighted Smogon statistics**.

## Data sources

- Showdown replay search: `https://replay.pokemonshowdown.com/search.json`
- Showdown replay JSON: `https://replay.pokemonshowdown.com/<battle-id>.json`
- Showdown user/ladder JSON: `https://pokemonshowdown.com/users/<user>.json`
- Showdown ladder JSON: `https://pokemonshowdown.com/ladder/<format>.json`
- Showdown Pokédex: `https://play.pokemonshowdown.com/data/pokedex.json`
- Showdown moves: `https://play.pokemonshowdown.com/data/moves.json`
- Smogon stats archive: `https://www.smogon.com/stats/<YYYY-MM>/chaos/<format>-<rating>.json.gz`

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

# One current Smogon snapshot
pokequant meta --month 2026-08 --format gen9ou --rating 1825

# Historical high-ladder Smogon warehouse
pokequant warehouse-meta \
  --db data/pokequant.db \
  --start 2023-01 \
  --end 2026-08 \
  --format gen9ou \
  --rating 1825

# Public replay corpus. limit=0 paginates until the API has no more results.
pokequant warehouse-replays \
  --db data/pokequant.db \
  --format gen9ou \
  --limit 0

# Inspect corpus size
pokequant warehouse-stats --db data/pokequant.db

# Time-decayed historical usage ranking; 3-month half-life by default
pokequant historical-rank \
  --db data/pokequant.db \
  --format gen9ou \
  --rating 1825 \
  --reference 2026-08 \
  --half-life 3

# Current-snapshot heuristic rankings
pokequant rank --month 2026-08 --format gen9ou --rating 1825 --top 30
pokequant optimize --month 2026-08 --format gen9ou --rating 1825 --pool 40
```

## Warehouse model

The database stores:

- monthly meta snapshot, rating cutoff, source URL, retrieval timestamp and parser version;
- Pokémon usage plus moves/items/abilities/Tera/teammate/check-counter payloads;
- public replay ID, format, upload time, ladder rating, players, winner and winner side;
- normalized team membership for both sides.

Replay ingestion is idempotent, so rerunning the same crawl does not duplicate battles. Historical weighting uses configurable exponential decay rather than treating old months as equally representative of the current metagame.

## Modeling rule

There is no permanently best team. The target is:

`argmax_T E[P(win | T, opponent distribution)] - risk penalty`

The repository must not label a heuristic candidate as the mathematical best team. That label is reserved for the later empirical matchup + Pokémon Showdown simulation pipeline.

## Roadmap

1. Historical warehouse and public replay corpus.
2. Empirical pair/core synergy, matchup matrix and robust win-probability objective.
3. Official Pokémon Showdown simulator integration and Monte Carlo/evolutionary search over teams and sets.

## License

MIT
