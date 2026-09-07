# Pokémon Quant

A quantitative Pokémon Showdown metagame and team-optimization project.

The objective is to estimate the legal six-Pokémon team that maximizes expected win probability against a target metagame, then explain why each slot was selected.

## V1 scope

- Pull public Pokémon Showdown replays through the official replay API.
- Pull monthly Smogon `chaos` metagame statistics.
- Parse battle logs into structured observations.
- Rank Pokémon using usage, set diversity, matchup evidence, and teammate synergy.
- Search six-Pokémon combinations with a beam-search optimizer.
- Emit a transparent team report with per-slot marginal value.

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
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .

# Download and summarize the current target meta
pokequant meta --month 2026-08 --format gen9ou --rating 1825

# Search and ingest public replays
pokequant replays --format gen9ou --limit 100

# Rank Pokémon
pokequant rank --month 2026-08 --format gen9ou --rating 1825 --top 30

# Generate a candidate six
pokequant optimize --month 2026-08 --format gen9ou --rating 1825 --pool 40
```

## Important modeling note

There is no permanently best team. The model optimizes against a specified opponent distribution and data window. Future milestones will add legality validation and Monte Carlo battle simulation using the official Pokémon Showdown simulator.

## License

MIT
