"""Deterministic, replay-bounded evidence packets for narrative generation.

The engine and validated synthetic fixture are authoritative. Callers supply an
insight ID and an observation minute, never facts or model-authored evidence.
"""

from __future__ import annotations

from .ai_schemas import ContextPacket, Fact, InclusiveWindow, InterpretationCode
from .engine import snapshot_for_minute
from .fixture import validate_fixture
from .models import MatchFixture

_BASE_LIMITATION = "Only recorded synthetic events are available; tactical causes are not established."


def _goal_interpretation(before: dict[str, int], after: dict[str, int], team_id: str) -> InterpretationCode:
    other = next(candidate for candidate in before if candidate != team_id)
    previous_gap = before[team_id] - before[other]
    current_gap = after[team_id] - after[other]
    if sum(before.values()) == 0:
        return "GOAL_OPENS_SCORING"
    if current_gap == 0:
        return "GOAL_EQUALIZES"
    if previous_gap <= 0 < current_gap:
        return "GOAL_TAKES_LEAD"
    if previous_gap > 0:
        return "GOAL_EXTENDS_LEAD"
    if current_gap < 0:
        return "GOAL_REDUCES_DEFICIT"
    return "GOAL_RECORDED"


def build_context(fixture: MatchFixture, insight_id: str, as_of_minute: int) -> ContextPacket:
    """Build facts for an engine insight available at an inclusive replay minute.

    Unknown and future insights deliberately share an unavailable error. The
    packet describes the moment's own facts even when inspected later in replay.
    """
    validate_fixture(fixture)
    snapshot = snapshot_for_minute(fixture, as_of_minute)
    card = next((item for item in snapshot["insights"] if item["id"] == insight_id), None)
    if card is None:
        raise ValueError("insight is unknown or unavailable at the requested minute")
    team_id = card["team_id"]
    evidence = card["evidence"]
    event_lookup = {event.id: event for event in fixture.events if event.minute <= card["minute"]}
    evidence_ids = list(card["evidence_event_ids"])
    if any(event_id not in event_lookup for event_id in evidence_ids):
        raise ValueError("insight references unavailable evidence")
    facts: list[Fact] = []
    limitations = [_BASE_LIMITATION]
    supported: list[InterpretationCode]
    if card["type"] == "goal":
        before, after = dict(evidence["score_before"]), dict(evidence["score_after"])
        facts.extend([
            Fact(id="score_before", metric="score_before", value=before),
            Fact(id="score_after", metric="score_after", value=after),
        ])
        for team in fixture.teams:
            facts.extend([
                Fact(id=f"goals_before_{team.id}", metric="goal_count", value=before[team.id], team_id=team.id, unit="goals"),
                Fact(id=f"goals_after_{team.id}", metric="goal_count", value=after[team.id], team_id=team.id, unit="goals"),
            ])
        player = next((item for item in fixture.players if item.id == evidence["player_id"]), None)
        if player is not None:
            facts.append(Fact(id="scorer_name", metric="scorer_name", value=player.name,
                              player_id=player.id, team_id=player.team_id))
        code = _goal_interpretation(before, after, team_id)
        supported = [code] if code == "GOAL_RECORDED" else [code, "GOAL_RECORDED"]
        limitations.append("The score transition is recorded; its tactical cause is not established.")
    elif card["type"] == "shot_surge":
        window = InclusiveWindow(start=evidence["window_start_minute_inclusive"],
                                 end=evidence["window_end_minute_inclusive"])
        for team in fixture.teams:
            facts.append(Fact(id=f"shots_{team.id}", metric="shot_count", value=evidence["shot_counts"][team.id],
                              team_id=team.id, unit="shots", window=window))
        supported = ["SHOT_SURGE"]
        limitations.append("Shot volume is not chance quality, expected goals, or proof of tactical pressure.")
    else:
        previous_window = InclusiveWindow(start=evidence["previous_window"][0], end=evidence["previous_window"][1])
        current_window = InclusiveWindow(start=evidence["current_window"][0], end=evidence["current_window"][1])
        for team in fixture.teams:
            previous = evidence["previous_possession_percent"][team.id]
            current = evidence["current_possession_percent"][team.id]
            facts.extend([
                Fact(id=f"possession_previous_{team.id}", metric="possession_percent", value=previous,
                     team_id=team.id, unit="percent", window=previous_window),
                Fact(id=f"possession_current_{team.id}", metric="possession_percent", value=current,
                     team_id=team.id, unit="percent", window=current_window),
                Fact(id=f"possession_delta_{team.id}", metric="possession_change_points", value=current - previous,
                     team_id=team.id, unit="percentage_points", window=current_window),
            ])
        supported = ["POSSESSION_INCREASE"]
        limitations.append("Measured possession time share does not establish tactical control or pressure.")
    return ContextPacket(
        match_id=fixture.match_id, fixture_version=fixture.fixture_version,
        insight_id=card["id"], insight_type=card["type"], minute=card["minute"],
        as_of_minute=as_of_minute, team_id=team_id,
        teams={team.id: team.name for team in fixture.teams}, facts=facts,
        evidence_event_ids=evidence_ids, supported_interpretations=supported,
        limitations=limitations,
    )
