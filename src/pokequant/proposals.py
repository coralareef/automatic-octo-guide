from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from pokequant.analysis.population import OpponentArchetype
from pokequant.evaluation import OpponentTeam
from pokequant.models import PokemonMeta
from pokequant.sets import generate_team_set_candidates


class ValidationLike(Protocol):
    valid: bool
    export: str


Validator = Callable[..., ValidationLike]


@dataclass(frozen=True, slots=True)
class ProposalBuildStats:
    archetypes_requested: int
    archetypes_covered: int
    exact_variants_tested: int
    legal_variants: int


def build_legal_opponent_proposals(
    archetypes: list[OpponentArchetype],
    records: dict[str, PokemonMeta],
    *,
    validator: Validator,
    format: str = "gen9ou",
    variants_per_archetype: int = 2,
    per_species: int = 6,
    beam_width: int = 64,
    proposal_limit: int = 32,
    coherence_floor: float = 0.20,
) -> tuple[list[OpponentTeam], ProposalBuildStats]:
    """Turn species archetypes into weighted coherent legal exact teams.

    The archetype probability is split across up to ``variants_per_archetype``
    legal set proposals in proportion to each proposal's marginal score. The
    final weights are renormalized if an archetype cannot produce a legal team.
    """
    outputs: list[OpponentTeam] = []
    tested = 0
    covered = 0
    legal_count = 0

    for index, archetype in enumerate(archetypes, start=1):
        variants = generate_team_set_candidates(
            archetype.members,
            records,
            per_species=per_species,
            beam_width=beam_width,
            limit=proposal_limit,
        )
        accepted: list[tuple[str, float]] = []
        for variant in variants:
            if min(candidate.coherence_score for candidate in variant.sets) < coherence_floor:
                continue
            tested += 1
            checked = validator(variant.export(), format=format)
            if not checked.valid:
                continue
            legal_count += 1
            accepted.append((checked.export, max(variant.marginal_score, 1e-12)))
            if len(accepted) >= variants_per_archetype:
                break

        if not accepted:
            continue
        covered += 1
        subtotal = sum(score for _, score in accepted)
        for variant_index, (team_export, score) in enumerate(accepted, start=1):
            outputs.append(
                OpponentTeam(
                    name=f"archetype-{index:02d}-set-{variant_index}",
                    team=team_export,
                    weight=archetype.proposal_probability * score / subtotal,
                    members=archetype.members,
                )
            )

    total = sum(row.weight for row in outputs)
    if total > 0:
        outputs = [
            OpponentTeam(
                name=row.name,
                team=row.team,
                weight=row.weight / total,
                members=row.members,
            )
            for row in outputs
        ]

    return outputs, ProposalBuildStats(
        archetypes_requested=len(archetypes),
        archetypes_covered=covered,
        exact_variants_tested=tested,
        legal_variants=legal_count,
    )
