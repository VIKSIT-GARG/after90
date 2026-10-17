"""Contract and cache checks for the complete HTTP surface."""

from fastapi.testclient import TestClient

from backend.matchlens import api as api_module
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


def test_explanation_and_recap_routes_use_the_same_verified_match(monkeypatch) -> None:
    for key in ("FOUNDRY_RESPONSES_URL", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"):
        monkeypatch.delenv(key, raising=False)
    client = TestClient(app)
    final = client.get("/api/matches/demo?minute=90").json()
    insight_id = next(item["id"] for item in final["insights"] if item["type"] == "goal")

    fan_response = client.get(f"/api/matches/demo/insights/{insight_id}?mode=fan")
    analyst_response = client.get(f"/api/matches/demo/insights/{insight_id}?mode=analyst")
    assert fan_response.status_code == analyst_response.status_code == 200
    fan, analyst = fan_response.json(), analyst_response.json()
    assert fan["insight_id"] == analyst["insight_id"] == insight_id
    assert fan["text"] != analyst["text"]
    assert fan["evidence"] == analyst["evidence"]
    assert fan["source"] == analyst["source"] == "template"

    recap = client.get("/api/matches/demo/recap?mode=analyst")
    assert recap.status_code == 200
    assert recap.json()["final_score"] == final["score"]
    assert recap.json()["stats"] == final["stats"]
    assert recap.json()["source"] == "template"
    assert client.get("/api/matches/demo/insights/not-real").status_code == 404
    assert client.get(f"/api/matches/demo/insights/{insight_id}?mode=expert").status_code == 422
    assert client.get("/api/matches/demo/recap?mode=expert").status_code == 422


def test_explanation_cache_is_scoped_by_fixture_insight_and_mode(monkeypatch) -> None:
    app.dependency_overrides[get_fixture] = tiny_fixture
    api_module._explanation_cache.clear()
    original = api_module.explain_insight
    calls = []

    def counted(fixture, insight, mode):
        calls.append((fixture.fixture_version, insight["id"], mode))
        return original(fixture, insight, mode)

    monkeypatch.setattr(api_module, "explain_insight", counted)
    try:
        client = TestClient(app)
        goal_id = client.get("/api/matches/demo?minute=90").json()["insights"][0]["id"]
        for mode in ("fan", "fan", "analyst", "analyst"):
            assert client.get(f"/api/matches/demo/insights/{goal_id}?mode={mode}").status_code == 200
        assert calls == [("test-v1", goal_id, "fan"), ("test-v1", goal_id, "analyst")]
    finally:
        app.dependency_overrides.clear()
        api_module._explanation_cache.clear()
