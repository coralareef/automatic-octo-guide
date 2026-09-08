from __future__ import annotations

from dataclasses import dataclass

from pokequant.analysis.population import OpponentArchetype


@dataclass(frozen=True, slots=True)
class StressRoster:
    style: str
    sample_name: str
    members: tuple[str, ...]


# Current SV OU sample-team structures used as deterministic robustness anchors.
# These are intentionally roster-only. Exact sets are regenerated from the same
# current Smogon chaos snapshot as the candidate and passed through Showdown's
# legality validator, so the stress suite does not freeze one historical paste.
CURRENT_OU_STRESS_ROSTERS: tuple[StressRoster, ...] = (
    StressRoster(
        style="screens_ho",
        sample_name="booster hands orb ceru glimmcard (screens vers)",
        members=(
            "Zamazenta",
            "Ceruledge",
            "Deoxys-Speed",
            "Glimmora",
            "Iron Hands",
            "Iron Valiant",
        ),
    ),
    StressRoster(
        style="sun_offense",
        sample_name="Zarude Sun",
        members=(
            "Walking Wake",
            "Great Tusk",
            "Ninetales",
            "Cresselia",
            "Zarude",
            "Ceruledge",
        ),
    ),
    StressRoster(
        style="bulky_offense",
        sample_name="GargTreads",
        members=(
            "Gholdengo",
            "Garganacl",
            "Iron Treads",
            "Moltres",
            "Samurott-Hisui",
            "Zamazenta",
        ),
    ),
    StressRoster(
        style="hazard_stack",
        sample_name="Spikestack",
        members=(
            "Gliscor",
            "Darkrai",
            "Dragonite",
            "Gholdengo",
            "Ting-Lu",
            "Zamazenta",
        ),
    ),
    StressRoster(
        style="fat_balance",
        sample_name="Samu Bliss Tealpon Fat",
        members=(
            "Ogerpon",
            "Blissey",
            "Gliscor",
            "Pecharunt",
            "Samurott-Hisui",
            "Skarmory",
        ),
    ),
    StressRoster(
        style="pivot_balance",
        sample_name="Pivots Bandza",
        members=(
            "Weezing-Galar",
            "Alomomola",
            "Iron Treads",
            "Lokix",
            "Tornadus-Therian",
            "Zamazenta",
        ),
    ),
    StressRoster(
        style="stall",
        sample_name="Mandibuzz Talonflame peaked 2108",
        members=(
            "Dondozo",
            "Blissey",
            "Gliscor",
            "Mandibuzz",
            "Talonflame",
            "Toxapex",
        ),
    ),
)


def stress_archetypes() -> list[OpponentArchetype]:
    """Return an equal-weight robustness suite, not a ladder probability model."""
    if not CURRENT_OU_STRESS_ROSTERS:
        return []
    weight = 1.0 / len(CURRENT_OU_STRESS_ROSTERS)
    return [
        OpponentArchetype(
            members=row.members,
            score=0.0,
            proposal_probability=weight,
            usage_component=0.0,
            association_component=0.0,
        )
        for row in CURRENT_OU_STRESS_ROSTERS
    ]
