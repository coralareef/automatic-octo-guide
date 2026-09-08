# Pokémon Quant

A quantitative Pokémon Showdown metagame and team-optimization project.

The objective is to estimate the legal six-Pokémon team that maximizes expected win probability against a target metagame, then explain why each slot was selected.

## Current status

The project now includes:

- a reproducible SQLite warehouse for historical Smogon/Pokémon Showdown-derived statistics and public Showdown replays;
- time-decayed historical metagame aggregation;
- replay-derived Pokémon outcomes, pair lift/PMI and matchup estimates;
- threat-coverage and opponent-population models;
- exact-set generation with coherence filters;
- official Pokémon Showdown legality validation and battle simulation;
- paired side-swapped risk-adjusted evaluation;
- an interactive Streamlit evidence dashboard.

Default research target: **Gen 9 OU, August 2026 current legality, with historical 1825-weighted evidence from January 2023 through August 2026**.

The latest completed historical refinement run loaded **44 monthly snapshots and 10,152 Pokémon-stat rows**. Its current leading candidate is **Great Tusk / Zamazenta / Gholdengo / Samurott-Hisui / Dragonite / Kyurem**, but this remains a research leader rather than a final mathematical-best claim because the deeper Monte Carlo sample and policy are still being strengthened.

## Dashboard

Install the optional UI dependencies and launch:

```bash
pip install -e ".[dashboard]"
streamlit run dashboard/app.py
```

The dashboard opens in snapshot mode using `dashboard/latest_snapshot.json`. If `data/pokequant.db` exists, it additionally exposes live time-decayed historical rankings, public replay outcomes, pair synergy and empirical matchup estimates.

The UI is intentionally evidence-first. It displays confidence intervals, research gates and unresolved limitations rather than presenting the current leader as solved.

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

# Historical high-ladder metagame warehouse
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

# Time-decayed historical usage ranking
pokequant historical-rank \
  --db data/pokequant.db \
  --format gen9ou \
  --rating 1825 \
  --reference 2026-08 \
  --half-life 3

# Replay-derived evidence
pokequant empirical-pokemon --db data/pokequant.db --format gen9ou --min-rating 1400
pokequant empirical-pairs --db data/pokequant.db --format gen9ou --min-rating 1400
pokequant empirical-matchups --db data/pokequant.db --format gen9ou --min-rating 1400
```

## Warehouse model

The database stores:

- monthly meta snapshot, rating cutoff, source URL, retrieval timestamp and parser version;
- Pokémon usage plus moves/items/abilities/Tera/teammate/check-counter payloads;
- public replay ID, format, upload time, ladder rating, players, winner and winner side;
- normalized team membership for both sides.

Replay ingestion is idempotent. Historical weighting uses configurable exponential decay instead of treating old months as equally representative of the current metagame.

## Modeling rule

There is no permanently best team independent of the opponent population and ruleset. The target is:

`argmax_T E[P(win | T, opponent distribution)] - risk penalty`

Static usage/synergy/threat scores generate candidates. The final ranking must increasingly be driven by historical battle evidence, replay evidence and paired official Showdown simulations.

## End-game roadmap

1. Expand the public replay corpus and empirical outcome layer.
2. Blend 0 / 1695 / 1825 skill layers instead of relying on one cutoff alone.
3. Increase paired Monte Carlo sample size and opponent/set diversity.
4. Improve the battle decision policy beyond the current symmetric heuristic baseline.
5. Run held-out future-month backtests to detect overfitting.
6. Only then promote a candidate from “leading team” to a statistically defensible best-found team for the chosen metagame target.

## License

MIT
