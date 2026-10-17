"""Evidence, fallback, and mode behavior for synthetic match wording."""

import json

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.explanations import build_recap, explain_insight
from backend.matchlens.fixture import load_fixture


def _goal():
    fixture = load_fixture()
    goal = next(card for card in snapshot_for_minute(fixture, 90)["insights"]
                if card["type"] == "goal")
    return fixture, goal


def test_modes_change_only_wording_and_preserve_engine_evidence(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    fixture, goal = _goal()
    tampered = {**goal, "evidence": {"score_after": {"blue": 99}}}
    fan = explain_insight(fixture, tampered, "fan")
    analyst = explain_insight(fixture, tampered, "analyst")
    assert fan["text"] != analyst["text"]
    assert fan["source"] == analyst["source"] == "template"
    assert fan["evidence"] == analyst["evidence"]
    assert fan["evidence"]["score_after"] == goal["evidence"]["score_after"]
    assert fan["evidence"]["event_ids"] == goal["evidence_event_ids"]
    assert fan["insight_id"] == analyst["insight_id"] == goal["id"]


def test_valid_injected_response_is_used_and_cannot_edit_canonical_fields():
    fixture, goal = _goal()
    seen = []

    def client(payload):
        seen.append(payload)
        return {"output_text": "Northstar Quay scored (event e072).",
                "evidence": {"score_after": {"blue": 999}}}

    result = explain_insight(fixture, goal, "fan", client=client)
    assert result["source"] == "foundry"
    assert result["text"] == "Northstar Quay scored (event e072)."
    assert result["evidence"]["score_after"] == goal["evidence"]["score_after"]
    assert seen[0]["verified_facts"]["goal_event_id"] == "e072"


def test_fabricated_number_player_and_event_are_rejected():
    fixture, goal = _goal()
    for text in (
        "Northstar Quay scored 99 goals.",
        "Northstar Quay scored zero goals.",
        "Marco scored at minute 29.",
        "Copper Vale scored at minute 29.",
        "Northstar Quay scored at minute 29 (event e999).",
    ):
        result = explain_insight(fixture, goal, "fan", client=lambda _payload: text)
        assert result["source"] == "template"
        assert result["text"] != text


def test_model_failure_and_weak_evidence_recap_use_templates():
    fixture = load_fixture()

    def failed(_payload):
        raise OSError("network unavailable")

    recap = build_recap(fixture, "fan", client=failed)
    assert recap["source"] == "template"
    assert recap["moment_ids"]

    # A sparse synthetic fixture must not generate a match narrative or moments.
    sparse = fixture.model_copy(update={"events": []})
    limited = build_recap(sparse, "fan")
    assert limited["moment_ids"] == []
    assert limited["final_score"] == {team.id: 0 for team in sparse.teams}
    assert "0 goals" in limited["text"]
    assert "Evidence is limited" in limited["text"]


def test_configured_foundry_adapter_posts_verified_facts_with_short_timeout(monkeypatch):
    fixture, goal = _goal()
    monkeypatch.setenv("FOUNDRY_RESPONSES_URL", "https://example.test/openai/v1/responses")
    monkeypatch.setenv("FOUNDRY_API_KEY", "test-key")
    monkeypatch.setenv("FOUNDRY_MODEL", "test-deployment")
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"output_text": "Northstar Quay scored."}).encode()

    def urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["key"] = request.get_header("Api-key")
        observed["body"] = json.loads(request.data)
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("backend.matchlens.explanations.urlopen", urlopen)
    result = explain_insight(fixture, goal, "fan")
    assert result["source"] == "foundry"
    assert observed["url"].endswith("/responses")
    assert observed["key"] == "test-key"
    assert observed["body"]["model"] == "test-deployment"
    assert observed["body"]["store"] is False
    assert '"goal_event_id": "e072"' in observed["body"]["input"][1]["content"]
    assert observed["timeout"] == 3


def test_recap_matches_final_snapshot_and_modes_share_facts():
    fixture = load_fixture()
    final = snapshot_for_minute(fixture, 90)
    fan = build_recap(fixture, "fan")
    analyst = build_recap(fixture, "analyst")
    assert fan["text"] != analyst["text"]
    assert fan["final_score"] == analyst["final_score"] == final["score"]
    assert fan["stats"] == analyst["stats"] == final["stats"]
    assert fan["moment_ids"] == analyst["moment_ids"] == [
        card["id"] for card in final["insights"] if card["type"] == "goal"
    ]


def test_recap_rejects_unsupported_claims_and_accepts_grounded_text():
    fixture = load_fixture()
    fabricated = build_recap(fixture, "analyst", client=lambda _payload:
                             "Copper Vale had 900 shots.")
    assert fabricated["source"] == "template"
    grounded = build_recap(fixture, "fan", client=lambda _payload:
                           "The final snapshot records goals, shots and passes.")
    assert grounded["source"] == "foundry"


def test_supported_numbers_with_wrong_team_attribution_fall_back():
    fixture = load_fixture()
    final = snapshot_for_minute(fixture, 90)
    surge = next(card for card in final["insights"] if card["type"] == "shot_surge")
    # Three is a real count, but it belongs to Northstar Quay in this window.
    wrong_shots = explain_insight(
        fixture, surge, "analyst", client=lambda _payload: "Copper Vale took 3 shots."
    )
    assert wrong_shots["source"] == "template"
    assert wrong_shots["evidence"]["shot_counts"] == surge["evidence"]["shot_counts"]

    # Both digits occur in the final score, but the team assignment is reversed.
    wrong_score = build_recap(
        fixture, "analyst", client=lambda _payload: "Copper Vale 2–1 Northstar Quay."
    )
    assert wrong_score["source"] == "template"
    assert wrong_score["final_score"] == final["score"]


def test_model_cannot_describe_a_different_insight_metric():
    fixture = load_fixture()
    final = snapshot_for_minute(fixture, 90)
    surge = next(card for card in final["insights"] if card["type"] == "shot_surge")
    wrong_metric = explain_insight(
        fixture, surge, "fan", client=lambda _payload: "Northstar Quay scored."
    )
    assert wrong_metric["source"] == "template"


def test_invalid_mode_or_unknown_insight_is_rejected():
    fixture, goal = _goal()
    import pytest

    with pytest.raises(ValueError):
        explain_insight(fixture, goal, "expert")
    with pytest.raises(ValueError):
        build_recap(fixture, "expert")
    with pytest.raises(ValueError):
        explain_insight(fixture, {"id": "made-up"}, "fan")
