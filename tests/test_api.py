"""Contract checks for the phase-two HTTP surface."""

from fastapi.testclient import TestClient

from backend.matchlens.api import app, get_fixture
from backend.matchlens.models import MatchEvent, MatchFixture, Player, Team


def tiny_fixture() -> MatchFixture:
    return MatchFixture(
        match_id="demo",
        fixture_version="test-v1",
        synthetic=True,
        initial_possession_team_id="blue",
        teams=[Team(id="blue", name="Harbor Blue"), Team(id="red", name="Valley Red")],
        players=[
            Player(id="blue_09", team_id="blue", name="Ari Vale"),
            Player(id="red_01", team_id="red", name="Rin Sol"),
        ],
        events=[
            MatchEvent(id="e001", minute=1, type="pass", team_id="blue", player_id="blue_09"),
            MatchEvent(id="e002", minute=3, type="shot", team_id="blue", player_id="blue_09"),
            MatchEvent(
                id="e003", minute=3, second=1, type="goal", team_id="blue",
                player_id="blue_09", related_event_id="e002",
            ),
        ],
    )


def test_health_and_snapshot_contract() -> None:
    app.dependency_overrides[get_fixture] = tiny_fixture
    try:
        client = TestClient(app)
        assert client.get("/api/health").json() == {
            "status": "ok", "fixture_version": "test-v1", "synthetic": True,
        }
        before = client.get("/api/matches/demo?minute=0")
        assert before.status_code == 200
        assert before.json()["score"] == {"blue": 0, "red": 0}
        after = client.get("/api/matches/demo?minute=3")
        assert after.status_code == 200
        payload = after.json()
        assert payload["match_id"] == "demo"
        assert payload["synthetic"] is True
        assert payload["score"] == {"blue": 1, "red": 0}
        assert payload["stats"]["shots"] == {"blue": 1, "red": 0}
    finally:
        app.dependency_overrides.clear()


def test_minute_bounds_are_rejected() -> None:
    app.dependency_overrides[get_fixture] = tiny_fixture
    try:
        client = TestClient(app)
        assert client.get("/api/matches/demo?minute=-1").status_code == 422
        assert client.get("/api/matches/demo?minute=91").status_code == 422
        assert client.get("/api/matches/demo?minute=oops").status_code == 422
    finally:
        app.dependency_overrides.clear()
