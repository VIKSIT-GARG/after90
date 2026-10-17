"""Replay behavior against small fixtures independent of the demo file."""

import pytest

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.models import MatchFixture


def fixture_with(*events: dict, initial: str = "blue") -> MatchFixture:
    return MatchFixture.model_validate(
        {
            "match_id": "tiny",
            "fixture_version": "tiny-v1",
            "synthetic": True,
            "initial_possession_team_id": initial,
            "teams": [
                {"id": "blue", "name": "Harbor Blue"},
                {"id": "red", "name": "Valley Red"},
            ],
            "players": [],
            "events": list(events),
        }
    )


def event(event_id: str, minute: int, kind: str, team: str = "blue", **fields) -> dict:
    return {
        "id": event_id,
        "minute": minute,
        "type": kind,
        "team_id": team,
        **fields,
    }


def test_snapshot_counts_linked_goal_once_and_never_reveals_future_events():
    fixture = fixture_with(
        event("p1", 0, "pass"),
        event("s1", 5, "shot", player_id="blue_9"),
        event("g1", 5, "goal", player_id="blue_9", related_event_id="s1"),
        event("p2", 6, "pass", "red"),
        event("s2", 20, "shot", "red"),
    )

    zero = snapshot_for_minute(fixture, 0)
    assert zero["synthetic"] is True
    assert zero["score"] == {"blue": 0, "red": 0}
    assert zero["stats"]["shots"] == {"blue": 0, "red": 0}
    assert zero["stats"]["passes"] == {"blue": 1, "red": 0}
    assert [item["id"] for item in zero["recent_events"]] == ["p1"]
    assert zero["insights"] == []

    five = snapshot_for_minute(fixture, 5)
    assert five["score"] == {"blue": 1, "red": 0}
    assert five["stats"]["shots"] == {"blue": 1, "red": 0}
    assert five["stats"]["passes"] == {"blue": 1, "red": 0}
    assert [item["id"] for item in five["recent_events"]] == ["p1", "s1", "g1"]
    goal = five["insights"][0]
    assert goal["id"] == "goal-g1"
    assert goal["evidence_event_ids"] == ["g1", "s1"]
    assert goal["evidence"]["score_before"] == {"blue": 0, "red": 0}
    assert goal["evidence"]["score_after"] == {"blue": 1, "red": 0}

    twenty = snapshot_for_minute(fixture, 20)
    assert twenty["stats"]["shots"] == {"blue": 1, "red": 1}
    assert [item["id"] for item in twenty["recent_events"]] == ["s2"]
    assert [item["id"] for item in twenty["insights"]] == ["goal-g1"]


def test_shot_surge_crosses_threshold_once_and_replay_is_deterministic():
    fixture = fixture_with(
        event("s1", 2, "shot"),
        event("s2", 4, "shot"),
        event("r1", 5, "shot", "red"),
        event("s3", 6, "shot"),
        event("s4", 7, "shot"),
        event("later", 30, "pass"),
    )
    six = snapshot_for_minute(fixture, 6)
    surge = six["insights"][0]
    assert surge["id"] == "surge-6-blue"
    assert surge["type"] == "shot_surge"
    assert surge["evidence_event_ids"] == ["s1", "s2", "r1", "s3"]
    assert surge["evidence"]["shot_counts"] == {"blue": 3, "red": 1}
    assert surge["evidence"]["window_start_minute_inclusive"] == 0
    assert [card["id"] for card in snapshot_for_minute(fixture, 7)["insights"]] == [
        "surge-6-blue"
    ]
    assert snapshot_for_minute(fixture, 0)["insights"] == []
    assert snapshot_for_minute(fixture, 6) == six


def test_early_surge_window_includes_minute_zero_shot():
    fixture = fixture_with(
        event("at-zero", 0, "shot"),
        event("at-one", 1, "shot"),
        event("at-two", 2, "shot"),
    )
    surge = snapshot_for_minute(fixture, 2)["insights"][0]
    assert surge["evidence_event_ids"] == ["at-zero", "at-one", "at-two"]
    assert surge["evidence"]["window_start_minute_inclusive"] == 0
    assert surge["evidence"]["window_end_minute_inclusive"] == 2


def test_possession_uses_timestamps_and_swing_requires_both_windows():
    fixture = fixture_with(
        event("c1", 2, "possession_change", "red", possession_team_id="red"),
        event("c2", 12, "possession_change", "blue", possession_team_id="blue"),
        event("c3", 14, "possession_change", "red", possession_team_id="red"),
        event("c4", 17, "possession_change", "blue", possession_team_id="blue"),
    )
    nineteen = snapshot_for_minute(fixture, 19)
    assert nineteen["stats"]["possession_percent"] == {"blue": 35, "red": 65}
    swing = nineteen["insights"][0]
    assert swing["id"] == "swing-19-blue"
    assert swing["type"] == "possession_swing"
    assert swing["evidence_event_ids"] == ["c1", "c2", "c3", "c4"]
    assert swing["evidence"]["previous_possession_percent"] == {
        "blue": 20,
        "red": 80,
    }
    assert swing["evidence"]["current_possession_percent"] == {
        "blue": 50,
        "red": 50,
    }
    assert swing["evidence"]["change_points"] == 30
    assert sum(nineteen["stats"]["possession_percent"].values()) == 100
    assert [card["id"] for card in snapshot_for_minute(fixture, 20)["insights"]] == [
        "swing-19-blue"
    ]

    sparse = fixture_with(
        event("only", 12, "possession_change", "red", possession_team_id="red")
    )
    assert snapshot_for_minute(sparse, 19)["insights"] == []


def test_possession_uses_seconds_and_rounds_to_exactly_one_hundred():
    fixture = fixture_with(
        event(
            "change",
            0,
            "possession_change",
            "red",
            second=20,
            possession_team_id="red",
        )
    )
    zero = snapshot_for_minute(fixture, 0)
    assert zero["stats"]["possession_percent"] == {"blue": 33, "red": 67}
    assert sum(zero["stats"]["possession_percent"].values()) == 100


@pytest.mark.parametrize("minute", [-1, 91, 2.5, True, "5"])
def test_invalid_minute_is_rejected(minute):
    with pytest.raises(ValueError, match="minute"):
        snapshot_for_minute(fixture_with(), minute)
