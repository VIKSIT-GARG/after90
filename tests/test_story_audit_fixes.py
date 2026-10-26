"""Regression cases for AI-03 sparse possession and AI-04 pattern starvation."""

import pytest

from backend.matchlens.evaluation import fixture_for_scenario
from backend.matchlens.fixture import load_fixture, validate_fixture
from backend.matchlens.models import MatchEvent
from backend.matchlens.story import build_recap_context, build_story


def _high_scoring_fixture():
    fixture = load_fixture().model_copy(deep=True)
    events = []
    for event in fixture.events:
        if event.id in {"e012", "e054", "e061", "e068"}:
            event = event.model_copy(update={"outcome": "goal"})
            events.append(event)
            events.append(MatchEvent(
                id="audit-goal-" + event.id,
                minute=event.minute, second=event.second + 1, type="goal",
                team_id=event.team_id, player_id=event.player_id,
                possession_team_id=event.possession_team_id,
                related_event_id=event.id,
            ))
        else:
            events.append(event)
    fixture.events = events
    validate_fixture(fixture)
    return fixture


@pytest.mark.parametrize("scenario", ["empty", "goalless"])
def test_recap_without_transitions_omits_assumption_derived_possession(scenario):
    fixture = fixture_for_scenario(scenario)
    assert not any(event.type == "possession_change" for event in fixture.events)
    packet = build_recap_context(fixture)
    facts = {fact.id: fact.value for fact in packet.facts}
    assert facts["possession_available"] == 0
    assert not any(fact.id.startswith("possession_") and fact.team_id is not None
                   for fact in packet.facts)
    assert any("Measured possession is unavailable" in limitation
               and "assumption" in limitation for limitation in packet.limitations)
    # Other supported facts remain available despite the absent possession data.
    assert "final_score" in facts
    assert all(f"shots_{team.id}" in facts for team in fixture.teams)


def test_golden_recap_retains_recorded_possession_comparison():
    fixture = load_fixture()
    facts = {fact.id: fact.value for fact in build_recap_context(fixture).facts}
    assert facts["possession_available"] == 1
    assert facts["possession_blue"] == 53
    assert facts["possession_red"] == 47


def test_high_score_preserves_goals_and_each_supported_pattern_type():
    fixture = _high_scoring_fixture()
    ledger = build_story(fixture)
    goals = [moment for moment in ledger["all_moments"] if moment["type"] == "goal"]
    selected = ledger["moments"]
    assert len(goals) == 7
    assert {moment["id"] for moment in goals} <= {moment["id"] for moment in selected}
    assert {moment["type"] for moment in selected} == {
        "goal", "shot_surge", "possession_swing",
    }
    assert len([moment for moment in selected if moment["type"] != "goal"]) <= 6
    assert [moment["minute"] for moment in selected] == sorted(moment["minute"] for moment in selected)
    facts = {fact.id: fact.value for fact in build_recap_context(fixture).facts}
    assert {moment["type"] for moment in facts["story_summary"]} == {
        "goal", "shot_surge", "possession_swing",
    }


@pytest.mark.parametrize("cap", [1, 2, 3, 6])
def test_high_score_pattern_allowance_is_bounded_even_when_goals_exceed_cap(cap):
    ledger = build_story(_high_scoring_fixture(), max_moments=cap)
    selected = ledger["moments"]
    assert len([moment for moment in selected if moment["type"] == "goal"]) == 7
    patterns = [moment for moment in selected if moment["type"] != "goal"]
    assert 1 <= len(patterns) <= cap
    assert len({moment["type"] for moment in patterns}) == min(cap, 2)


def test_pattern_reservation_preserves_original_metric_windows_and_provenance():
    fixture = _high_scoring_fixture()
    ledger = build_story(fixture)
    for moment in ledger["moments"]:
        assert moment["group_window"][0] <= moment["window"][0]
        assert moment["window"][1] <= moment["group_window"][1]
        assert set(moment["evidence_event_ids"]) <= {event.id for event in fixture.events}
        if moment["type"] == "possession_swing":
            evidence = moment["evidence"]
            assert moment["window"] == [evidence["previous_window"][0], evidence["current_window"][1]]
