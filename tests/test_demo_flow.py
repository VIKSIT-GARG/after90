"""End-to-end checks for the checked-in fixture through the public snapshot API."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.matchlens.api import app
from backend.matchlens.fixture import load_fixture


def test_golden_match_replays_with_all_evidence_backed_insight_types() -> None:
    client = TestClient(app)
    start = client.get("/api/matches/demo?minute=0")
    full_time = client.get("/api/matches/demo?minute=90")

    assert start.status_code == full_time.status_code == 200
    assert start.json()["score"] == {"blue": 0, "red": 0}
    final = full_time.json()
    assert final["synthetic"] is True
    assert final["score"] == {"blue": 2, "red": 1}
    assert final["stats"]["shots"] == {"blue": 10, "red": 6}
    assert sum(final["stats"]["possession_percent"].values()) == 100
    assert {insight["type"] for insight in final["insights"]} == {
        "goal", "shot_surge", "possession_swing",
    }

    fixture_events = {event.id: event for event in load_fixture().events}
    for insight in final["insights"]:
        assert insight["evidence_event_ids"]
        assert len(insight["evidence_event_ids"]) == len(set(insight["evidence_event_ids"]))
        for event_id in insight["evidence_event_ids"]:
            assert event_id in fixture_events
            assert fixture_events[event_id].minute <= insight["minute"]

    assert client.get("/api/matches/demo?minute=90").json() == final


def test_frontend_handoff_sample_matches_the_real_api() -> None:
    sample_path = Path(__file__).resolve().parents[1] / "docs" / "samples" / "snapshot-minute-29.json"
    expected = json.loads(sample_path.read_text(encoding="utf-8"))
    response = TestClient(app).get("/api/matches/demo?minute=29")
    assert response.status_code == 200
    assert response.json() == expected
