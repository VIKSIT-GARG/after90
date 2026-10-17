"""Behavior checks for the checked-in synthetic match fixture."""

import json
from collections import Counter

import pytest

from backend.matchlens.fixture import DEFAULT_FIXTURE_PATH, load_fixture, validate_fixture


def _edited_fixture(tmp_path, edit):
    raw = json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    edit(raw)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_golden_fixture_loads_identically_from_any_working_directory(monkeypatch, tmp_path):
    first = load_fixture()
    monkeypatch.chdir(tmp_path)
    second = load_fixture()

    assert first.model_dump() == second.model_dump()
    assert first.match_id == "demo"
    assert first.fixture_version == "v1"
    assert first.synthetic is True
    assert first.events[0].minute == 0
    assert first.events[-1].minute == 90

    goals = Counter(event.team_id for event in first.events if event.type == "goal")
    assert goals == {"blue": 2, "red": 1}
    assert len([event for event in first.events if event.type == "shot"]) == 16


def test_fixture_events_have_stable_references_order_and_insight_windows():
    fixture = load_fixture()
    validate_fixture(fixture)
    event_ids = {event.id for event in fixture.events}
    assert len(event_ids) == len(fixture.events)
    assert [event.id for event in fixture.events] == [
        f"e{number:03d}" for number in range(1, len(fixture.events) + 1)
    ]
    assert [(event.minute, event.second) for event in fixture.events] == sorted(
        (event.minute, event.second) for event in fixture.events
    )
    assert all(event.related_event_id in event_ids for event in fixture.events if event.type == "goal")

    # The authored story supports a shot surge and adjacent possession windows.
    surge = [event for event in fixture.events if 20 < event.minute <= 30 and event.type == "shot"]
    assert sum(event.team_id == "blue" for event in surge) >= 3
    assert sum(event.team_id == "red" for event in surge) == 0
    previous_changes = [
        event for event in fixture.events
        if event.type == "possession_change" and 19 <= event.minute < 29
    ]
    current_changes = [
        event for event in fixture.events
        if event.type == "possession_change" and 29 <= event.minute < 39
    ]
    assert previous_changes and current_changes


def test_goal_must_link_to_an_earlier_matching_shot(tmp_path):
    path = _edited_fixture(
        tmp_path,
        lambda raw: next(event for event in raw["events"] if event["type"] == "goal").update(
            related_event_id="e001"
        ),
    )
    with pytest.raises(ValueError, match="goal must link to an earlier shot"):
        load_fixture(path)


def test_non_synthetic_fixture_is_rejected(tmp_path):
    path = _edited_fixture(tmp_path, lambda raw: raw.update(synthetic=False))
    with pytest.raises(ValueError, match="synthetic"):
        load_fixture(path)


def test_invalid_possession_transition_is_rejected(tmp_path):
    path = _edited_fixture(
        tmp_path,
        lambda raw: next(
            event for event in raw["events"] if event["type"] == "possession_change"
        ).update(team_id="blue", possession_team_id="blue"),
    )
    with pytest.raises(ValueError, match="possession change must switch teams"):
        load_fixture(path)
