"""Evidence and chronology checks for story grouping and recap inputs."""

import pytest

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture, validate_fixture
from backend.matchlens.models import MatchEvent
from backend.matchlens.story import build_recap_context, build_story


def _score_fixture(scoring):
    """Make valid score scenarios independent of the golden event order."""
    base = load_fixture()
    players = {team.id: next(p.id for p in base.players if p.team_id == team.id) for team in base.teams}
    holder = base.initial_possession_team_id
    events = []
    for index, (minute, team) in enumerate(scoring):
        if team != holder:
            events.append(MatchEvent(id=f"change-{index}", minute=minute, second=0,
                                    type="possession_change", team_id=team,
                                    possession_team_id=team))
            holder = team
        shot_id = f"shot-{index}"
        events.append(MatchEvent(id=shot_id, minute=minute, second=10, type="shot",
                                team_id=team, player_id=players[team], outcome="goal", possession_team_id=holder))
        events.append(MatchEvent(id=f"goal-{index}", minute=minute, second=20, type="goal",
                                team_id=team, player_id=players[team], related_event_id=shot_id,
                                possession_team_id=holder))
    result = base.model_copy(update={"events": events})
    validate_fixture(result)
    return result


def test_golden_story_keeps_goals_and_patterns_with_canonical_provenance():
    fixture = load_fixture()
    ledger = build_story(fixture)
    moments = ledger["moments"]
    assert {moment["type"] for moment in moments} == {"goal", "shot_surge", "possession_swing"}
    assert len([moment for moment in moments if moment["type"] == "goal"]) == 3
    assert len(moments) <= 6
    assert [item["minute"] for item in moments] == sorted(item["minute"] for item in moments)
    canonical = {item["id"]: item for item in snapshot_for_minute(fixture, 90)["insights"]}
    for moment in ledger["all_moments"]:
        members = [canonical[member] for member in moment["member_insight_ids"]]
        expected = {event_id for member in members for event_id in member["evidence_event_ids"]}
        assert set(moment["evidence_event_ids"]) == expected
        representative = canonical[moment["id"]]
        assert moment["evidence"] == representative["evidence"]
        if moment["type"] == "possession_swing":
            assert moment["window"] == [representative["evidence"]["previous_window"][0], representative["evidence"]["current_window"][1]]
        assert moment["group_window"][0] <= moment["window"][0] <= moment["window"][1] <= moment["group_window"][1]
        assert all(member["type"] == moment["type"] and member["team_id"] == moment["team_id"] for member in members)
    assert any(len(moment["member_insight_ids"]) > 1 for moment in ledger["all_moments"])


def test_live_story_does_not_depend_on_future_events_or_claim_winner():
    fixture = load_fixture()
    minute = 24
    visible = fixture.model_copy(update={"events": [event for event in fixture.events if event.minute <= minute]})
    validate_fixture(visible)
    assert build_story(fixture, minute) == build_story(visible, minute)
    for cutoff in (0, 24, 29, 57, 89):
        ledger = build_story(fixture, cutoff)
        allowed = {event.id for event in fixture.events if event.minute <= cutoff}
        assert all(moment["minute"] <= cutoff and not moment["winning_goal"] for moment in ledger["all_moments"])
        assert all(set(moment["evidence_event_ids"]) <= allowed for moment in ledger["all_moments"])
    assert len([moment for moment in build_story(fixture)["moments"] if moment["winning_goal"]]) == 1


def test_replay_is_deterministic_and_does_not_mutate_the_fixture():
    fixture = load_fixture()
    before = fixture.model_dump()
    full = build_story(fixture)
    build_story(fixture, 0)
    assert build_story(fixture) == full
    assert fixture.model_dump() == before


def test_recap_fact_totals_match_final_snapshot_and_include_non_goal_stories():
    fixture = load_fixture()
    packet = build_recap_context(fixture)
    final = snapshot_for_minute(fixture, 90)
    facts = {fact.id: fact.value for fact in packet.facts}
    assert packet.minute == packet.as_of_minute == 90
    assert packet.supported_interpretations == ["MATCH_RECAP"]
    assert facts["final_score"] == final["score"]
    for team in fixture.teams:
        assert facts[f"shots_{team.id}"] == final["stats"]["shots"][team.id]
        assert facts[f"passes_{team.id}"] == final["stats"]["passes"][team.id]
        assert facts[f"possession_{team.id}"] == final["stats"]["possession_percent"][team.id]
    assert {item["type"] for item in facts["story_summary"]} == {"goal", "shot_surge", "possession_swing"}
    assert facts["selected_moment_ids"] == [moment["id"] for moment in build_story(fixture)["moments"]]
    assert facts["goal_minutes"] == [29, 62, 78]


def test_empty_fixture_recap_is_explicitly_limited_without_invented_moments():
    fixture = _score_fixture([])
    packet = build_recap_context(fixture)
    facts = {fact.id: fact.value for fact in packet.facts}
    assert facts["final_score"] == {team.id: 0 for team in fixture.teams}
    assert facts["selected_moment_ids"] == facts["goal_minutes"] == facts["story_summary"] == []
    assert "LIMITED_EVIDENCE" in packet.supported_interpretations
    assert any("no events" in limitation for limitation in packet.limitations)
    assert packet.evidence_event_ids == []


def test_draw_has_no_winning_goal_and_comeback_uses_correct_score_context():
    fixture = _score_fixture([(10, "red"), (40, "blue")])
    assert not any(moment["winning_goal"] for moment in build_story(fixture)["moments"])
    comeback = _score_fixture([(10, "red"), (40, "blue"), (80, "blue")])
    moments = build_story(comeback)["moments"]
    assert [moment["interpretation_code"] for moment in moments] == [
        "GOAL_OPENS_SCORING", "GOAL_EQUALIZES", "GOAL_TAKES_LEAD"]
    assert [moment["minute"] for moment in moments if moment["winning_goal"]] == [80]
    assert not any(moment["winning_goal"] for moment in build_story(comeback, 80)["moments"])


def test_presentation_cap_never_discards_goals():
    fixture = _score_fixture([(minute, "blue") for minute in [5, 15, 25, 35, 45, 55, 65]])
    ledger = build_story(fixture, max_moments=3)
    assert len(ledger["moments"]) == 7
    assert all(moment["type"] == "goal" for moment in ledger["moments"])


@pytest.mark.parametrize("minute", [True, -1, 91, 1.5])
def test_invalid_replay_minute_rejected(minute):
    with pytest.raises(ValueError):
        build_story(load_fixture(), minute)


@pytest.mark.parametrize("cap", [True, 0, -1, 1.5])
def test_invalid_presentation_cap_rejected(cap):
    with pytest.raises(ValueError):
        build_story(load_fixture(), max_moments=cap)
