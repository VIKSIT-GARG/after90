"""Validate bounded model selections against canonical match evidence.

Free-form model prose is deliberately outside this contract. The server renders
facts with team, window and outcome attribution after these checks pass.
"""

from __future__ import annotations

from typing import Any

from .ai_schemas import ContextPacket, NarrativeSelection


def required_fact_ids(packet: ContextPacket) -> set[str]:
    """Evidence needed to support the packet's core interpretation."""
    if packet.insight_type == "goal":
        return {"score_before", "score_after"}
    if packet.insight_type == "shot_surge":
        return {f"shots_{team}" for team in packet.teams}
    if packet.insight_type == "possession_swing":
        return {f"possession_{period}_{packet.team_id}" for period in ("previous", "current", "delta")}
    if packet.insight_type == "recap":
        required = {"final_score", "selected_moment_ids", "story_summary", "goal_minutes"}
        if any(fact.id == "possession_available" for fact in packet.facts):
            required.add("possession_available")
        return required
    return {fact.id for fact in packet.facts}


def validate_selection(value: Any, packet: ContextPacket) -> NarrativeSelection:
    """Reject unsupported interpretations, facts, prose, or incomplete support.

    Contexts come from the engine, not clients. The comparison closure below also
    prevents a model citing one team's count while rendering a two-team result.
    """
    selection = NarrativeSelection.model_validate(value).validate_against(packet)
    selected = set(selection.selected_fact_ids)
    available = {fact.id for fact in packet.facts}
    required = required_fact_ids(packet)
    if not required <= available:
        raise ValueError("canonical context is missing required interpretation facts")
    if not required <= selected:
        raise ValueError("selection omits required supporting facts")
    if packet.insight_type == "recap":
        for prefix in ("shots", "passes", "possession"):
            pair = {f"{prefix}_{team}" for team in packet.teams}
            if selected & pair and not pair <= selected:
                raise ValueError("recap comparisons must select both team facts")
    return selection
