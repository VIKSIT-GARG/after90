"""Versioned evidence contracts and a bounded, model-selectable narrative plan.

NarrativeSelection is the only model-authored structure. NarrativeOutput is
server-rendered: arbitrary prose is never made trustworthy by schema validation.
"""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

SCHEMA_VERSION = "1.0"
InterpretationCode = Literal[
    "GOAL_OPENS_SCORING", "GOAL_EQUALIZES", "GOAL_TAKES_LEAD",
    "GOAL_EXTENDS_LEAD", "GOAL_REDUCES_DEFICIT", "GOAL_RECORDED",
    "SHOT_SURGE", "POSSESSION_INCREASE", "LIMITED_EVIDENCE", "MATCH_RECAP",
]
InsightType = Literal["goal", "shot_surge", "possession_swing", "recap", "limited_evidence"]
Source = Literal["foundry", "template"]
FactValue = StrictInt | StrictFloat | StrictStr | list[JsonValue] | dict[str, JsonValue]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class InclusiveWindow(ContractModel):
    start: int = Field(ge=0, le=90)
    end: int = Field(ge=0, le=90)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("window end must not precede start")
        return self


class Fact(ContractModel):
    id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    value: FactValue
    team_id: str | None = None
    player_id: str | None = None
    unit: str | None = None
    window: InclusiveWindow | None = None

    @field_validator("value")
    @classmethod
    def finite_json(cls, value: FactValue) -> FactValue:
        def visit(item: JsonValue) -> None:
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("fact values must be finite JSON values")
            if isinstance(item, list):
                for child in item:
                    visit(child)
            if isinstance(item, dict):
                for child in item.values():
                    visit(child)
        visit(value)
        return value


class ContextPacket(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    match_id: str = Field(min_length=1)
    fixture_version: str = Field(min_length=1)
    insight_id: str = Field(min_length=1)
    insight_type: InsightType
    minute: int = Field(ge=0, le=90)
    as_of_minute: int = Field(ge=0, le=90)
    team_id: str | None = None
    teams: dict[str, str]
    facts: list[Fact]
    evidence_event_ids: list[str]
    supported_interpretations: list[InterpretationCode] = Field(min_length=1)
    limitations: list[str]

    @model_validator(mode="after")
    def evidence_invariants(self) -> Self:
        if self.minute > self.as_of_minute:
            raise ValueError("insight minute must not exceed as_of_minute")
        if self.insight_type == "recap" and (self.minute != 90 or self.as_of_minute != 90):
            raise ValueError("full-time recap requires minute 90")
        if len(self.teams) != 2 or any(not key.strip() or not name.strip() for key, name in self.teams.items()):
            raise ValueError("exactly two named teams are required")
        if self.team_id is not None and self.team_id not in self.teams:
            raise ValueError("focus team must belong to this fixture")
        for values, label in [(self.evidence_event_ids, "event IDs"), ([f.id for f in self.facts], "fact IDs"),
                              (self.supported_interpretations, "interpretations"), (self.limitations, "limitations")]:
            if len(values) != len(set(values)) or any(not value.strip() for value in values):
                raise ValueError(f"{label} must be unique and nonempty strings")
        for fact in self.facts:
            if fact.team_id is not None and fact.team_id not in self.teams:
                raise ValueError("fact team must belong to this fixture")
            if fact.window is not None and fact.window.end > self.as_of_minute:
                raise ValueError("fact window must not include future minutes")
        return self


class NarrativeSelection(ContractModel):
    """The model chooses evidence and approved framing, never factual prose.

    Every field is required and extras are forbidden for strict structured output.
    The service must additionally call validate_against for the specific packet.
    """

    selected_fact_ids: list[str] = Field(min_length=1)
    interpretation_code: InterpretationCode
    fan_frame: Literal["concise", "contextual"]
    analyst_frame: Literal["evidence", "comparison"]
    limitations: list[str]

    def validate_against(self, packet: ContextPacket) -> Self:
        if len(self.selected_fact_ids) != len(set(self.selected_fact_ids)):
            raise ValueError("selected facts must be unique")
        if not set(self.selected_fact_ids) <= {fact.id for fact in packet.facts}:
            raise ValueError("selected facts must belong to the supplied packet")
        if self.interpretation_code not in packet.supported_interpretations:
            raise ValueError("interpretation must be supported by the supplied packet")
        if len(self.limitations) != len(set(self.limitations)) or not set(self.limitations) <= set(packet.limitations):
            raise ValueError("limitations must be a unique subset of packet limitations")
        return self


class NarrativeOutput(ContractModel):
    """Server-rendered paired wording; never trust model prose as this type."""

    headline: str = Field(min_length=1, max_length=120)
    selected_fact_ids: list[str] = Field(min_length=1)
    interpretation_code: InterpretationCode
    fan_explanation: str = Field(min_length=1, max_length=1200)
    analyst_explanation: str = Field(min_length=1, max_length=2400)
    limitations: list[str]

    def validate_against(self, packet: ContextPacket) -> Self:
        NarrativeSelection(selected_fact_ids=self.selected_fact_ids, interpretation_code=self.interpretation_code,
                           fan_frame="concise", analyst_frame="evidence", limitations=self.limitations).validate_against(packet)
        return self


class GenerationMetadata(ContractModel):
    source: Source
    fallback_reason: str | None
    model_version: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    latency_ms: float = Field(ge=0)

    @model_validator(mode="after")
    def truthful_source(self) -> Self:
        if self.source == "foundry" and self.fallback_reason is not None:
            raise ValueError("Foundry output must not have a fallback reason")
        if self.source == "template" and (self.fallback_reason is None or not self.fallback_reason.strip()):
            raise ValueError("template output must explain why fallback was used")
        return self


class Overlay(ContractModel):
    insight_id: str = Field(min_length=1)
    match_minute: int = Field(ge=0, le=90)
    headline: str = Field(min_length=1, max_length=120)
    stat_line: str = Field(min_length=1, max_length=240)
    display_duration_ms: int = Field(ge=1000, le=30000)
    priority: Literal["low", "medium", "high"]
    evidence_event_ids: list[str]
    source: Source
    synthetic: Literal[True] = True


class ValidationMetadata(ContractModel):
    """Selection-validation outcome, distinct from quality of fallback wording."""

    passed: bool
    reason: str | None
    transport: Literal["foundry", "injected", "offline"]


class NarrativeResult(NarrativeOutput):
    """Service envelope with internally consistent evidence and provenance.

    Wording is still server-rendered; these checks validate the envelope, not the
    semantic truth of arbitrary text or successful live evaluation.
    """

    source: Source
    selection_source: Literal["foundry", "injected", "deterministic"]
    selection_accepted: bool
    selection: NarrativeSelection
    metadata: GenerationMetadata
    validation: ValidationMetadata
    evidence: ContextPacket

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        if self.source != self.metadata.source:
            raise ValueError("result and metadata source must agree")
        if self.validation.passed != self.selection_accepted:
            raise ValueError("selection acceptance and validation result must agree")
        if self.validation.reason != self.metadata.fallback_reason:
            raise ValueError("validation and fallback reasons must agree")
        if self.source == "foundry":
            if not self.selection_accepted or self.selection_source != "foundry" or self.validation.transport != "foundry":
                raise ValueError("Foundry provenance requires accepted Foundry selection and transport")
        elif self.selection_accepted:
            if self.selection_source != "injected" or self.validation.transport != "injected":
                raise ValueError("accepted template-labelled selection must identify injected provenance")
            if self.metadata.fallback_reason != "injected_client":
                raise ValueError("injected selection must retain an explicit injected-client reason")
        elif self.selection_source != "deterministic":
            raise ValueError("unaccepted selection must use deterministic fallback")
        if self.validation.transport == "offline" and (self.selection_accepted or self.selection_source != "deterministic"):
            raise ValueError("offline generation cannot claim accepted model selection")
        if self.selected_fact_ids != self.selection.selected_fact_ids or self.interpretation_code != self.selection.interpretation_code:
            raise ValueError("rendered output and selected facts/interpretation must agree")
        self.selection.validate_against(self.evidence)
        if self.limitations != self.evidence.limitations:
            raise ValueError("rendered output must retain canonical limitations")
        return self
