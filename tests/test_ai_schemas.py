"""Behavior checks for the evidence and model selection boundary."""

import pytest
from pydantic import ValidationError

from backend.matchlens.ai_schemas import ContextPacket, Fact, GenerationMetadata, NarrativeSelection


def packet(**updates):
    data = dict(match_id="synthetic", fixture_version="v1", insight_id="goal-e1", insight_type="goal",
                minute=29, as_of_minute=29, team_id="blue", teams={"blue": "Northstar", "red": "Copper"},
                facts=[Fact(id="score", metric="score_after", value={"blue": 1, "red": 0})],
                evidence_event_ids=["e1"], supported_interpretations=["GOAL_OPENS_SCORING"],
                limitations=["No tracking evidence"])
    return ContextPacket(**(data | updates))


def selection(**updates):
    return NarrativeSelection(**(dict(selected_fact_ids=["score"], interpretation_code="GOAL_OPENS_SCORING",
                                    fan_frame="contextual", analyst_frame="comparison", limitations=[]) | updates))


def test_model_selection_is_bounded_to_supplied_evidence_and_interpretation():
    assert selection().validate_against(packet()).selected_fact_ids == ["score"]
    for update in [dict(selected_fact_ids=["made-up"]), dict(selected_fact_ids=["score", "score"]),
                   dict(interpretation_code="GOAL_EQUALIZES"), dict(limitations=["invented limitation"])]:
        with pytest.raises(ValueError):
            selection(**update).validate_against(packet())
    with pytest.raises(ValidationError):
        NarrativeSelection(**selection().model_dump(), fan_explanation="Northstar did not score")


def test_temporal_and_entity_invariants_reject_future_or_wrong_team_facts():
    for update in [dict(as_of_minute=28), dict(team_id="unknown"), dict(evidence_event_ids=["e1", "e1"]),
                   dict(facts=[Fact(id="a", metric="shots", value=2, team_id="unknown")]),
                   dict(facts=[Fact(id="a", metric="shots", value=2, window={"start": 20, "end": 30})])]:
        with pytest.raises(ValidationError):
            packet(**update)
    with pytest.raises(ValidationError):
        packet(insight_type="recap")


def test_facts_are_strict_and_finite_and_round_trip_json():
    context = packet()
    assert ContextPacket.model_validate_json(context.model_dump_json()) == context
    for value in [True, None, float("nan"), {"nested": float("inf")}]:
        with pytest.raises(ValidationError):
            Fact(id="bad", metric="shots", value=value)
    with pytest.raises(ValidationError):
        packet(minute="29")


def test_selection_schema_is_closed_and_requires_every_field():
    schema = NarrativeSelection.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


def test_provenance_cannot_mislabel_a_fallback_as_foundry():
    GenerationMetadata(source="template", fallback_reason="not_configured", model_version="none", prompt_version="v1", latency_ms=0)
    for source, reason in [("foundry", "timeout"), ("template", None), ("template", "")]:
        with pytest.raises(ValidationError):
            GenerationMetadata(source=source, fallback_reason=reason, model_version="m", prompt_version="v1", latency_ms=1)


def result_data():
    from backend.matchlens.ai_schemas import NarrativeResult
    context = packet()
    chosen = selection()
    data = dict(headline="Recorded goal", selected_fact_ids=chosen.selected_fact_ids,
                interpretation_code=chosen.interpretation_code, fan_explanation="A recorded goal.",
                analyst_explanation="The recorded score changed.", limitations=context.limitations,
                source="template", selection_source="deterministic", selection_accepted=False,
                selection=chosen.model_dump(), evidence=context.model_dump(),
                metadata=dict(source="template", fallback_reason="offline", model_version="unconfigured",
                              prompt_version="v1", latency_ms=0),
                validation=dict(passed=False, reason="offline", transport="offline"))
    return NarrativeResult, data


def test_result_envelope_preserves_truthful_offline_and_injected_provenance():
    Result, data = result_data()
    offline = Result.model_validate(data)
    assert Result.model_validate_json(offline.model_dump_json()) == offline
    data.update(selection_source="injected", selection_accepted=True)
    data["metadata"]["fallback_reason"] = "injected_client"
    data["validation"].update(passed=True, reason="injected_client", transport="injected")
    assert Result.model_validate(data).source == "template"


def test_result_envelope_accepts_foundry_only_with_matching_accepted_transport():
    Result, data = result_data()
    data.update(source="foundry", selection_source="foundry", selection_accepted=True)
    data["metadata"].update(source="foundry", fallback_reason=None, model_version="deployed-model")
    data["validation"].update(passed=True, reason=None, transport="foundry")
    assert Result.model_validate(data).source == "foundry"
    data["validation"]["transport"] = "injected"
    with pytest.raises(ValidationError, match="Foundry provenance"):
        Result.model_validate(data)


@pytest.mark.parametrize("change", [
    {"source": "foundry"},
    {"selection_source": "injected"},
    {"selection_accepted": True},
    {"selected_fact_ids": ["other"]},
    {"limitations": []},
    {"validation": {"passed": True, "reason": "offline", "transport": "offline"}},
    {"validation": {"passed": False, "reason": "timeout", "transport": "offline"}},
])
def test_result_envelope_rejects_mislabelling_or_evidence_drift(change):
    Result, data = result_data()
    with pytest.raises(ValidationError):
        Result.model_validate(data | change)
