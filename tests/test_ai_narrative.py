"""Offline narrative-contract tests; injected/mocked clients are not live proof."""

import json

import pytest

from backend.matchlens.ai_schemas import ContextPacket, Fact
from backend.matchlens.context import build_context
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.narrative import generate_narrative, selection_schema
from backend.matchlens.validation import required_fact_ids, validate_selection


@pytest.fixture
def fixture():
    return load_fixture()


@pytest.fixture
def packet(fixture):
    card = next(card for card in snapshot_for_minute(fixture, 90)["insights"] if card["type"] == "goal")
    return build_context(fixture, card["id"], card["minute"])


def selection(packet, **updates):
    return {
        "selected_fact_ids": [fact.id for fact in packet.facts],
        "interpretation_code": packet.supported_interpretations[0],
        "fan_frame": "contextual", "analyst_frame": "comparison",
        "limitations": list(packet.limitations), **updates,
    }


def test_unconfigured_generation_is_explainable_fallback(packet, monkeypatch):
    for name in ("FOUNDRY_RESPONSES_URL", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"):
        monkeypatch.delenv(name, raising=False)
    result = generate_narrative(packet)
    assert result["source"] == "template"
    assert result["metadata"]["fallback_reason"] == "not_configured"
    assert result["selection_source"] == "deterministic"
    assert result["selection_accepted"] is False
    assert result["fan_explanation"] != result["analyst_explanation"]
    assert result["evidence"] == packet.model_dump(mode="json")


def test_injected_success_never_claims_live_foundry(packet):
    result = generate_narrative(packet, client=lambda _: selection(packet))
    assert result["selection_accepted"] is True
    assert result["selection_source"] == "injected"
    assert result["source"] == "template"
    assert result["metadata"]["fallback_reason"] == "injected_client"
    assert result["limitations"] == packet.limitations


@pytest.mark.parametrize("updates", [
    {"fan_explanation": "Northstar Quay did not score."},
    {"headline": "Copper Vale scored."},
    {"selected_fact_ids": ["future_goal"]},
    {"selected_fact_ids": ["score_after", "score_after"]},
    {"selected_fact_ids": ["scorer_name"]},
    {"interpretation_code": "POSSESSION_INCREASE"},
    {"interpretation_code": "GOAL_DID_NOT_HAPPEN"},
    {"fan_frame": "because of pressing"},
    {"analyst_frame": "reversed_score"},
    {"limitations": ["The opponent had zero shots"]},
])
def test_unsupported_references_prose_negations_and_frames_fall_back(packet, updates):
    result = generate_narrative(packet, client=lambda _: selection(packet, **updates))
    assert result["selection_accepted"] is False
    assert result["source"] == "template"
    assert result["metadata"]["fallback_reason"] == "invalid_selection"
    assert result["evidence"] == packet.model_dump(mode="json")


@pytest.mark.parametrize("response,reason", [
    ("Northstar Quay did not score.", "malformed_response"),
    ("{broken", "malformed_response"),
    ({"refusal": "No"}, "model_refusal"),
    ({"status": "incomplete", "output_text": "{}"}, "incomplete_response"),
    ({"output": [{"content": [{"type": "refusal", "refusal": "No"}]}]}, "model_refusal"),
    ({"output": "not a list"}, "malformed_response"),
    (None, "malformed_response"),
])
def test_service_refusal_and_incomplete_or_malformed_output(packet, response, reason):
    result = generate_narrative(packet, client=lambda _: response)
    assert result["source"] == "template"
    assert result["selection_accepted"] is False
    assert result["metadata"]["fallback_reason"] == reason


@pytest.mark.parametrize("error,reason", [(TimeoutError("secret-key"), "timeout"), (OSError("secret-key"), "invalid_selection")])
def test_client_errors_are_sanitized(packet, error, reason):
    def failed(_):
        raise error
    result = generate_narrative(packet, client=failed)
    assert result["metadata"]["fallback_reason"] == reason
    assert "secret-key" not in json.dumps(result)


def test_dynamic_schema_only_offers_supplied_choices(packet):
    schema = selection_schema(packet)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["interpretation_code"]["enum"] == packet.supported_interpretations
    assert schema["properties"]["selected_fact_ids"]["items"]["enum"] == [fact.id for fact in packet.facts]


def test_every_golden_insight_renders_with_consistent_evidence(fixture):
    for card in snapshot_for_minute(fixture, 90)["insights"]:
        packet = build_context(fixture, card["id"], card["minute"])
        result = generate_narrative(packet, client=lambda _: selection(packet))
        assert result["selection_accepted"] is True
        assert result["fan_explanation"] != result["analyst_explanation"]
        assert result["evidence"]["as_of_minute"] == card["minute"]
        assert set(result["selected_fact_ids"]) >= required_fact_ids(packet)
        assert "tactics caused" not in result["analyst_explanation"]


def test_selected_goal_scorer_is_optional_but_scores_are_not(packet):
    without_scorer = [fact.id for fact in packet.facts if fact.id != "scorer_name"]
    result = generate_narrative(packet, client=lambda _: selection(packet, selected_fact_ids=without_scorer))
    assert result["selection_accepted"] is True
    scorer = next(fact.value for fact in packet.facts if fact.id == "scorer_name")
    assert scorer not in result["analyst_explanation"]
    with pytest.raises(ValueError, match="supporting"):
        validate_selection(selection(packet, selected_fact_ids=["score_after"]), packet)


def test_valid_json_envelope_and_frames_change_presentation_only(packet):
    raw = selection(packet, fan_frame="concise", analyst_frame="evidence")
    result = generate_narrative(packet, client=lambda _: {"output": [{"content": [{"type": "output_text", "text": json.dumps(raw)}]}]})
    other = generate_narrative(packet, client=lambda _: selection(packet))
    assert result["selection_accepted"] is True
    assert result["fan_explanation"] != other["fan_explanation"]
    assert result["analyst_explanation"] != other["analyst_explanation"]
    assert result["evidence"] == other["evidence"]


def test_mocked_transport_checks_request_contract_and_labels_success(packet, monkeypatch):
    # This intercepts HTTP in-process; it deliberately is not evidence of live access.
    from backend.matchlens import narrative
    monkeypatch.setenv("FOUNDRY_RESPONSES_URL", "https://test-resource.openai.azure.com/openai/v1/responses")
    monkeypatch.setenv("FOUNDRY_MODEL", "test-deployment")
    monkeypatch.setenv("FOUNDRY_API_KEY", "secret-key")
    observed = {}
    from backend.matchlens.provider import ProviderResponse
    def request_json(url, key, body, *, timeout, max_bytes):
        observed.update(body=body, timeout=timeout, max_bytes=max_bytes)
        return ProviderResponse(
            {"status": "completed", "output_text": json.dumps(selection(packet))},
            {"provider_response_id": "resp-test", "provider_model": "returned-model",
             "input_tokens": 40, "output_tokens": 20, "total_tokens": 60, "provider_request_ms": 1.2})
    monkeypatch.setattr(narrative, "request_json", request_json)
    result = generate_narrative(packet)
    assert result["source"] == "foundry"
    assert result["selection_accepted"] is True
    assert result["metadata"]["fallback_reason"] is None
    assert result["metadata"]["provider_attempted"] is True
    assert result["metadata"]["provider"]["provider_model"] == "returned-model"
    assert result["metadata"]["provider"]["total_tokens"] == 60
    assert observed["timeout"] == 3
    assert observed["body"]["store"] is False
    assert observed["body"]["text"]["format"]["strict"] is True
    assert "secret-key" not in json.dumps(result)


@pytest.mark.parametrize("url", [
    "http://resource.openai.azure.com/openai/v1/responses",
    "https://resource.openai.azure.com.evil.test/openai/v1/responses",
    "https://user:password@resource.openai.azure.com/openai/v1/responses",
    "https://resource.openai.azure.com/openai/v1/responses?api-key=secret",
    "https://resource.openai.azure.com:444/openai/v1/responses",
])
def test_unsafe_endpoints_are_not_called(packet, monkeypatch, url):
    monkeypatch.setenv("FOUNDRY_RESPONSES_URL", url)
    monkeypatch.setenv("FOUNDRY_API_KEY", "key")
    monkeypatch.setenv("FOUNDRY_MODEL", "deployment")
    result = generate_narrative(packet)
    assert result["metadata"]["fallback_reason"] == "invalid_endpoint"


def test_explicit_offline_mode_never_calls_transport(packet, monkeypatch):
    from backend.matchlens import narrative
    monkeypatch.setattr(narrative, "_call_foundry", lambda _: pytest.fail("offline call attempted transport"))
    result = generate_narrative(packet, allow_live=False)
    assert result["metadata"]["fallback_reason"] == "offline"
    assert result["validation"]["transport"] == "offline"
    assert result["source"] == "template"


def test_recap_prioritizes_decisive_goals_and_retains_a_pattern(fixture):
    from backend.matchlens.story import build_recap_context
    packet = build_recap_context(fixture)
    result = generate_narrative(packet, allow_live=False)
    assert "equalizing goal" in result["fan_explanation"]
    assert "winning goal" in result["fan_explanation"]
    assert "shot surge" in result["fan_explanation"] or "possession increase" in result["fan_explanation"]
    assert result["evidence"] == packet.model_dump(mode="json")


def test_large_recap_caps_rendered_moments_without_dropping_evidence(fixture):
    from backend.matchlens.story import build_recap_context
    packet = build_recap_context(fixture)
    raw = packet.model_dump(mode="json")
    story = next(fact for fact in raw["facts"] if fact["id"] == "story_summary")
    story["value"] = [
        {"id": f"moment-{minute}", "type": "goal", "minute": minute, "team_id": "blue",
         "interpretation_code": "GOAL_EXTENDS_LEAD", "evidence_event_ids": [], "winning_goal": minute == 78}
        for minute in range(1, 79)
    ]
    packet = ContextPacket.model_validate(raw)
    result = generate_narrative(packet, allow_live=False)
    assert len(result["fan_explanation"]) <= 1200
    assert len(result["analyst_explanation"]) <= 2400
    assert "Additional moments remain available" in result["analyst_explanation"]
    assert len(next(f for f in result["evidence"]["facts"] if f["id"] == "story_summary")["value"]) == 78


def test_provider_schema_omits_unsupported_array_constraints(packet):
    schema = selection_schema(packet)
    forbidden = {"minItems", "maxItems", "uniqueItems", "contains", "minContains", "maxContains"}
    def visit(node):
        if isinstance(node, dict):
            assert not forbidden & node.keys()
            for value in node.values(): visit(value)
        elif isinstance(node, list):
            for value in node: visit(value)
    visit(schema)
    # Provider shape constraints do not replace local nonempty validation.
    result = generate_narrative(packet, client=lambda _: selection(packet, selected_fact_ids=[]))
    assert result["selection_accepted"] is False


def test_custom_generation_exception_cannot_leak_secrets(packet):
    from backend.matchlens.narrative import GenerationFailure
    def failed(_): raise GenerationFailure("secret-key")
    result = generate_narrative(packet, client=failed)
    assert result["metadata"]["fallback_reason"] == "invalid_selection"
    assert "secret-key" not in json.dumps(result)
