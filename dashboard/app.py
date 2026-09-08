from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from pokequant.analysis.empirical import matchup_matrix, pair_synergies, pokemon_outcomes
from pokequant.analysis.historical import weighted_usage
from pokequant.storage import connect, corpus_stats

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = Path(__file__).with_name("latest_snapshot.json")


@st.cache_data
def load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def roster(value: list[str] | tuple[str, ...]) -> str:
    return " / ".join(value)


def db_exists(path: str) -> bool:
    return bool(path) and Path(path).expanduser().exists()


def status_icon(status: str) -> str:
    key = status.casefold()
    if key in {"complete", "implemented"}:
        return "✅"
    if key in {"partial", "baseline"}:
        return "🟡"
    return "⬜"


snapshot = load_snapshot()
target = snapshot["target"]
evidence = snapshot["evidence"]
lead = snapshot["leading_candidate"]

st.set_page_config(
    page_title="Pokémon Quant",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
    .pq-kicker {font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; opacity: .65;}
    .pq-team {font-weight: 700; font-size: 1.05rem; line-height: 1.4;}
    .pq-note {font-size: .88rem; opacity: .75;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="pq-kicker">Pokémon Showdown quantitative research</div>', unsafe_allow_html=True)
st.title("Pokémon Quant — Evidence Dashboard")
st.caption(
    "Historical battle statistics → candidate generation → exact legal sets → "
    "paired Pokémon Showdown simulations. The UI distinguishes observed evidence "
    "from model assumptions and does not label a low-sample leader as solved."
)

with st.sidebar:
    st.header("Research target")
    st.write(f"**Format:** {target['format']}")
    st.write(f"**Current month:** {target['current_month']}")
    st.write(f"**Skill weighting:** {target['rating']}")
    st.write(
        f"**History:** {target['historical_start']} → {target['historical_end']}"
    )
    st.write(f"**Time-decay half-life:** {target['half_life_months']} months")
    st.divider()
    db_path = st.text_input("Local warehouse", value="data/pokequant.db")
    has_db = db_exists(db_path)
    if has_db:
        st.success("Warehouse connected")
    else:
        st.info("Snapshot mode. Add data/pokequant.db for replay-level views.")
    st.caption(
        "The committed snapshot is from the latest completed historical refinement "
        f"workflow run #{snapshot['generated_from']['run_id']}."
    )

overview, history_tab, replay_tab, team_tab, matchup_tab, method_tab = st.tabs(
    [
        "Overview",
        "Historical Meta",
        "Replay Evidence",
        "Team Lab",
        "Matchups",
        "Methodology",
    ]
)

with overview:
    st.subheader("Current research state")
    a, b, c, d, e = st.columns(5)
    a.metric("Historical snapshots", evidence["historical_snapshots"], border=True)
    b.metric("Pokémon-stat rows", f"{evidence['pokemon_rows']:,}", border=True)
    c.metric("Current eligible species", evidence["eligible_current_species"], border=True)
    d.metric("Leading sim win rate", pct(lead["expected_win"]), border=True)
    e.metric("95% interval", f"{pct(lead['ci_low'])}–{pct(lead['ci_high'])}", border=True)

    st.warning(
        "**Leading candidate, not final.** The 74.6% figure comes from the deeper "
        f"second-stage screen with {lead['configured_simulator_battles']} configured "
        "paired simulator battles. The interval is still too wide for an end-game claim."
    )

    st.markdown("### Leading six")
    cols = st.columns(6)
    for idx, name in enumerate(lead["members"], start=1):
        with cols[idx - 1]:
            with st.container(border=True):
                st.caption(f"SLOT {idx}")
                st.markdown(f"**{name}**")

    st.markdown("### Why this dashboard exists")
    left, right = st.columns([1.1, 1])
    with left:
        st.write(
            "The dashboard is a research instrument: it makes the evidence chain visible "
            "and gives us somewhere to inspect model failures before increasing compute."
        )
        st.dataframe(
            [
                {
                    "Evidence layer": "Historical Showdown-derived Smogon chaos",
                    "Use": "usage, teammates, sets, checks/counters, candidate prior",
                    "State": "active",
                },
                {
                    "Evidence layer": "Public Showdown replays",
                    "Use": "win outcomes, pair lift/PMI, matchup estimates",
                    "State": "warehouse-dependent",
                },
                {
                    "Evidence layer": "Official Showdown simulator",
                    "Use": "legal validation + paired expected-win testing",
                    "State": "active",
                },
                {
                    "Evidence layer": "Hand-written heuristics",
                    "Use": "set coherence + baseline battle decisions only",
                    "State": "secondary",
                },
            ],
            hide_index=True,
            width="stretch",
        )
    with right:
        gate_rows = []
        for row in snapshot["research_gates"]:
            gate_rows.append(
                {
                    "": status_icon(row["status"]),
                    "Gate": row["gate"],
                    "Status": row["status"],
                }
            )
        st.dataframe(gate_rows, hide_index=True, width="stretch")

with history_tab:
    st.subheader("Historical metagame evidence")
    st.caption(
        "Primary candidate-generation evidence is time-decayed multi-month battle-derived "
        "statistics, not one current-month opinion."
    )
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("First month", target["historical_start"], border=True)
    h2.metric("Last month", target["historical_end"], border=True)
    h3.metric("Months loaded", evidence["historical_snapshots"], border=True)
    h4.metric("Half-life", f"{target['half_life_months']} mo", border=True)

    if has_db:
        conn = connect(Path(db_path).expanduser())
        try:
            rows = weighted_usage(
                conn,
                format=target["format"],
                rating=int(target["rating"]),
                reference_month=target["current_month"],
                half_life_months=float(target["half_life_months"]),
            )[:30]
            rank_df = pd.DataFrame(
                [
                    {
                        "Pokémon": row.name,
                        "Time-decayed usage": row.weighted_usage,
                        "Snapshots": row.snapshots,
                        "Effective weight": row.effective_weight,
                    }
                    for row in rows
                ]
            )
            if not rank_df.empty:
                chart_df = rank_df.head(20).set_index("Pokémon")[["Time-decayed usage"]]
                st.bar_chart(chart_df)
                st.dataframe(
                    rank_df,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Time-decayed usage": st.column_config.NumberColumn(format="%.5f"),
                        "Effective weight": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            months = conn.execute(
                """
                SELECT month, rating, COUNT(*) AS pokemon_rows
                FROM meta_snapshots s
                JOIN pokemon_meta p ON p.snapshot_id=s.id
                WHERE s.format=?
                GROUP BY month, rating
                ORDER BY month DESC, rating DESC
                """,
                (target["format"],),
            ).fetchall()
            st.markdown("#### Warehouse coverage")
            st.dataframe([dict(row) for row in months], hide_index=True, width="stretch")
        finally:
            conn.close()
    else:
        st.info(
            "Connect the local SQLite warehouse to unlock the full historical ranking. "
            "The committed snapshot still verifies 44 monthly 1825 datasets and 10,152 "
            "Pokémon-stat rows were used in the latest tournament."
        )
        st.code(
            "pokequant warehouse-meta --db data/pokequant.db --start 2023-01 "
            "--end 2026-08 --format gen9ou --rating 1825",
            language="bash",
        )

with replay_tab:
    st.subheader("Public replay evidence")
    st.caption(
        "This tab intentionally separates public replay outcomes from Smogon aggregate "
        "statistics. Private raw ladder battles are not claimed as available."
    )
    if not has_db:
        st.info("Connect a replay-populated pokequant.db to inspect empirical outcomes.")
        st.code(
            "pokequant warehouse-replays --db data/pokequant.db --format gen9ou --limit 0",
            language="bash",
        )
    else:
        conn = connect(Path(db_path).expanduser())
        try:
            stats = corpus_stats(conn)
            r1, r2, r3 = st.columns(3)
            r1.metric("Public replays", f"{stats['replays']:,}", border=True)
            r2.metric("Team-member rows", f"{stats['team_members']:,}", border=True)
            rating_row = conn.execute(
                "SELECT MIN(rating) lo, MAX(rating) hi, COUNT(rating) n FROM replays WHERE format=?",
                (target["format"],),
            ).fetchone()
            rating_label = (
                f"{rating_row['lo']}–{rating_row['hi']}" if rating_row["n"] else "n/a"
            )
            r3.metric("Observed rating range", rating_label, border=True)

            min_rating = st.slider("Minimum replay rating", 1000, 1900, 1400, 50)
            outcomes = pokemon_outcomes(
                conn,
                format=target["format"],
                min_rating=min_rating,
                prior_strength=12.0,
            )[:30]
            st.markdown("#### Pokémon outcome association")
            st.dataframe(
                [
                    {
                        "Pokémon": row.name,
                        "Games": row.appearances,
                        "Wins": row.wins,
                        "Posterior win": row.posterior_win_rate,
                        "CI low": row.ci_low,
                        "CI high": row.ci_high,
                    }
                    for row in outcomes
                ],
                hide_index=True,
                width="stretch",
                column_config={
                    "Posterior win": st.column_config.NumberColumn(format="%.3f"),
                    "CI low": st.column_config.NumberColumn(format="%.3f"),
                    "CI high": st.column_config.NumberColumn(format="%.3f"),
                },
            )

            pairs = pair_synergies(
                conn,
                format=target["format"],
                min_rating=min_rating,
                min_pair_appearances=2,
            )[:30]
            st.markdown("#### Pair/core synergy")
            st.dataframe(
                [
                    {
                        "Pair": f"{row.a} + {row.b}",
                        "Team games": row.team_appearances,
                        "Lift": row.raw_lift,
                        "Shrunk PMI": row.shrunk_pmi,
                        "Pair posterior win": row.pair_posterior_win_rate,
                    }
                    for row in pairs
                ],
                hide_index=True,
                width="stretch",
            )
        finally:
            conn.close()

with team_tab:
    st.subheader("Team laboratory")
    st.caption(
        "Static scores are candidate-generation priors. Deeper simulator results are "
        "the more important ranking signal."
    )

    stage1_df = pd.DataFrame(
        [
            {
                "Team": roster(row["members"]),
                "Static score": row["static_score"],
                "Stage-1 win": row["expected_win"],
                "Objective": row["objective"],
                "Risk": row["risk"],
            }
            for row in snapshot["stage1_frontier"]
        ]
    ).sort_values("Objective", ascending=False)
    st.markdown("#### Candidate frontier")
    st.dataframe(
        stage1_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Stage-1 win": st.column_config.NumberColumn(format="%.3f"),
            "Objective": st.column_config.NumberColumn(format="%.3f"),
            "Risk": st.column_config.NumberColumn(format="%.3f"),
        },
    )

    finalist_df = pd.DataFrame(
        [
            {
                "Team": roster(row["members"]),
                "Expected win": row["expected_win"],
                "Objective": row["objective"],
                "Risk": row["risk"],
                "CI low": row["ci_low"],
                "CI high": row["ci_high"],
            }
            for row in snapshot["stage2_finalists"]
        ]
    ).sort_values("Objective", ascending=False)
    st.markdown("#### Deeper finalists")
    st.dataframe(finalist_df, hide_index=True, width="stretch")

    st.markdown("#### Current exact Showdown import")
    st.code(snapshot["exact_team_export"], language=None)
    st.caption(
        "This exact set package passed the official Gen 9 OU validator in the workflow, "
        "but set-level optimization is still ongoing."
    )

with matchup_tab:
    st.subheader("Leading candidate vs weighted opponent prototypes")
    matchup_df = pd.DataFrame(
        [
            {
                "Archetype": row["id"],
                "Opponent roster": roster(row["members"]),
                "Population weight": row["weight"],
                "Win rate": row["leading_candidate_win_rate"],
            }
            for row in snapshot["opponent_archetypes"]
        ]
    )
    chart_df = matchup_df.set_index("Archetype")[["Win rate"]]
    st.bar_chart(chart_df)
    st.dataframe(
        matchup_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Population weight": st.column_config.NumberColumn(format="%.3f"),
            "Win rate": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f"),
        },
    )
    st.caption(
        "These prototypes come from the historical statistical opponent model. A separate "
        "current-style stress suite exists to test screens, sun, hazard stack, balance and stall."
    )

    if has_db:
        conn = connect(Path(db_path).expanduser())
        try:
            empirical = matchup_matrix(
                conn,
                format=target["format"],
                min_rating=1400,
                min_observations=3,
            )[:50]
            if empirical:
                st.markdown("#### Public-replay directional matchup estimates")
                st.dataframe(
                    [
                        {
                            "A": row.attacker,
                            "B": row.defender,
                            "Observations": row.observations,
                            "Posterior A-win association": row.posterior_win_rate,
                            "CI low": row.ci_low,
                            "CI high": row.ci_high,
                        }
                        for row in empirical
                    ],
                    hide_index=True,
                    width="stretch",
                )
        finally:
            conn.close()

with method_tab:
    st.subheader("Methodology and end-game gates")
    st.latex(
        r"T^* = \\arg\\max_T \\left[\\mathbb{E}_{O\\sim P(O)}P(\\mathrm{win}\\mid T,O) - \\lambda\\,\\mathrm{Risk}(T)\\right]"
    )
    st.write(
        "The current workflow uses time-decayed historical 1825 battle-derived statistics "
        "to generate candidate species and opponent probabilities, current 1825 statistics "
        "for exact-set proposals, official Showdown validation, and paired side-swapped "
        "simulations. Public replay statistics can be added directly from the SQLite warehouse."
    )

    method_rows = []
    for row in snapshot["research_gates"]:
        method_rows.append(
            {
                "": status_icon(row["status"]),
                "Gate": row["gate"],
                "Status": row["status"],
                "What it means": row["detail"],
            }
        )
    st.dataframe(method_rows, hide_index=True, width="stretch")

    st.markdown("#### What still blocks an end-game claim")
    st.write(
        "The next statistical upgrades are larger Monte Carlo samples, 0/1695/1825 skill-layer "
        "blending, a stronger battle policy, more public replay evidence, and held-out future-month "
        "backtesting. The dashboard is intentionally built now so each upgrade can be measured "
        "rather than accepted on intuition."
    )
