"""Shared version-one data contract for fixtures and match events."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


EventType = Literal["pass", "shot", "tackle", "possession_change", "goal"]


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    team_id: str
    name: str


class MatchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    minute: int = Field(ge=0, le=90)
    second: int = Field(default=0, ge=0, le=59)
    type: EventType
    team_id: str
    player_id: str | None = None
    outcome: str | None = None
    possession_team_id: str | None = None
    related_event_id: str | None = None


class MatchFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_id: str
    fixture_version: str
    synthetic: Literal[True]
    initial_possession_team_id: str
    teams: list[Team]
    players: list[Player]
    events: list[MatchEvent]
