"""Replay-aware context and supported interpretation checks."""

import pytest

from backend.matchlens.context import build_context
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture, validate_fixture
from backend.matchlens.models import MatchFixture


def goal_fixture(scoring_teams: list[str]) -> MatchFixture:
    events = []
    holder = "blue"
    for index, team_id in enumerate(scoring_teams, start=1):
        minute = index * 10
        if team_id != holder:
            events.append({"id": f"c{index}", "minute": minute, "second": 0,
                           "type": "possession_change", "team_id": team_id, "possession_team_id": team_id})
            holder = team_id
        common = {"minute": minute, "team_id": team_id, "player_id": f"{team_id}_9", "possession_team_id": team_id}
        events.extend([
            {**common, "id": f"s{index}", "second": 1, "type": "shot", "outcome": "goal"},
            {**common, "id": f"g{index}", "second": 2, "type": "goal", "related_event_id": f"s{index}"},
        ])
    fixture = MatchFixture.model_validate({
        "match_id": "context-test", "fixture_version": "test-1", "synthetic": True,
        "initial_possession_team_id": "blue", "teams": [{"id": "blue", "name": "Harbor Blue"}, {"id": "red", "name": "Valley Red"}],
        "players": [{"id": f"{team}_9", "team_id": team, "name": f"Fictional {team.title()}"} for team in ["blue", "red"]],
        "events": events,
    })
    validate_fixture(fixture)
    return fixture


@pytest.mark.parametrize("sequence,goal_id,expected", [
    (["blue"], "goal-g1", "GOAL_OPENS_SCORING"),
    (["blue", "red"], "goal-g2", "GOAL_EQUALIZES"),
    (["blue", "red", "blue"], "goal-g3", "GOAL_TAKES_LEAD"),
    (["blue", "blue"], "goal-g2", "GOAL_EXTENDS_LEAD"),
    (["blue", "blue", "blue", "red"], "goal-g4", "GOAL_REDUCES_DEFICIT"),
])
def test_goal_context_classifies_verified_score_transition(sequence, goal_id, expected):
    fixture = goal_fixture(sequence)
    packet = build_context(fixture, goal_id, 90)
    assert packet.supported_interpretations == [expected, "GOAL_RECORDED"]
    facts = {fact.id: fact for fact in packet.facts}
    assert facts["score_after"].value == snapshot_for_minute(fixture, packet.minute)["score"]
    assert facts["scorer_name"].team_id == packet.team_id
    assert facts["scorer_name"].player_id == f"{packet.team_id}_9"


def test_canonical_goal_does_not_inherit_later_score_or_evidence():
    fixture = load_fixture()
    at_goal = build_context(fixture, "goal-e072", 29)
    later = build_context(fixture, "goal-e072", 90)
    assert {fact.id: fact.value for fact in later.facts}["score_after"] == {"blue": 1, "red": 0}
    assert at_goal.facts == later.facts
    assert later.evidence_event_ids == ["e072", "e071"]
    assert later.as_of_minute == 90


@pytest.mark.parametrize("insight_id,minute", [("goal-e072", 28), ("goal-e193", 77), ("made-up", 90)])
def test_future_and_unknown_insights_are_unavailable(insight_id, minute):
    with pytest.raises(ValueError, match="unknown or unavailable"):
        build_context(load_fixture(), insight_id, minute)


@pytest.mark.parametrize("minute", [-1, 91, True, "29", 29.5])
def test_invalid_replay_minute_is_rejected(minute):
    with pytest.raises(ValueError, match="minute"):
        build_context(load_fixture(), "goal-e072", minute)


def test_shot_surge_has_exact_team_attribution_and_window():
    packet = build_context(load_fixture(), "surge-28-blue", 28)
    facts = {fact.id: fact for fact in packet.facts}
    assert facts["shots_blue"].value == 3
    assert facts["shots_red"].value == 0
    assert facts["shots_blue"].team_id == "blue"
    assert facts["shots_red"].team_id == "red"
    assert facts["shots_blue"].window.model_dump() == {"start": 19, "end": 28}
    assert packet.supported_interpretations == ["SHOT_SURGE"]
    assert any("chance quality" in value for value in packet.limitations)


def test_possession_context_preserves_adjacent_windows_and_signed_deltas():
    packet = build_context(load_fixture(), "swing-20-blue", 20)
    facts = {fact.id: fact for fact in packet.facts}
    assert facts["possession_previous_blue"].value == 45
    assert facts["possession_current_blue"].value == 77
    assert facts["possession_delta_blue"].value == 32
    assert facts["possession_delta_red"].value == -32
    assert facts["possession_previous_blue"].window.model_dump() == {"start": 1, "end": 10}
    assert facts["possession_current_blue"].window.model_dump() == {"start": 11, "end": 20}
    assert packet.supported_interpretations == ["POSSESSION_INCREASE"]


def test_all_golden_contexts_have_only_available_evidence_and_finite_windows():
    fixture = load_fixture()
    events = {event.id: event for event in fixture.events}
    for card in snapshot_for_minute(fixture, 90)["insights"]:
        packet = build_context(fixture, card["id"], card["minute"])
        assert all(events[event_id].minute <= packet.minute for event_id in packet.evidence_event_ids)
        assert all(fact.window is None or fact.window.end <= packet.minute for fact in packet.facts)
        assert packet == build_context(fixture, card["id"], card["minute"])


def test_invalid_fixture_is_rejected_and_returned_facts_do_not_mutate_fixture():
    fixture = load_fixture()
    invalid = fixture.model_copy(update={"initial_possession_team_id": "missing"})
    with pytest.raises(ValueError, match="initial_possession"):
        build_context(invalid, "goal-e072", 29)
    packet = build_context(fixture, "goal-e072", 29)
    next(fact for fact in packet.facts if fact.id == "score_after").value["blue"] = 99
    assert next(fact for fact in build_context(fixture, "goal-e072", 29).facts if fact.id == "score_after").value["blue"] == 1
