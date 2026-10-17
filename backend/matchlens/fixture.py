"""Load and validate the versioned, wholly synthetic demo match.

The checked-in JSON is the golden fixture. Goal events refer to a preceding
shot; only the goal event contributes to score, and only the shot to shots.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from .models import MatchFixture


DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_match.json"


def validate_fixture(fixture: MatchFixture) -> None:
    """Raise ValueError when references, order, or possession are inconsistent."""
    if fixture.synthetic is not True:
        raise ValueError("fixture must be marked synthetic: true")
    if not fixture.match_id or not fixture.fixture_version:
        raise ValueError("fixture needs a match_id and fixture_version")

    teams = {team.id: team for team in fixture.teams}
    if len(fixture.teams) != 2 or len(teams) != 2:
        raise ValueError("fixture must contain exactly two teams with distinct IDs")
    if any(not team.id or not team.name for team in fixture.teams):
        raise ValueError("every team needs a nonempty ID and name")
    if len({team.name for team in fixture.teams}) != 2:
        raise ValueError("fixture teams must have distinct names")
    if fixture.initial_possession_team_id not in teams:
        raise ValueError("initial_possession_team_id must identify a fixture team")

    players = {player.id: player for player in fixture.players}
    if len(players) != len(fixture.players):
        raise ValueError("player IDs must be unique")
    if any(not player.id or not player.name for player in fixture.players):
        raise ValueError("every player needs a nonempty ID and name")
    for player in fixture.players:
        if player.team_id not in teams:
            raise ValueError(f"player {player.id}: unknown team_id {player.team_id}")
    if any(not any(player.team_id == team_id for player in players.values()) for team_id in teams):
        raise ValueError("each team needs at least one player")

    seen = {}
    goal_shot_ids = set()
    possession_team_id = fixture.initial_possession_team_id
    previous_time = (-1, -1)
    for event in fixture.events:
        label = f"event {event.id or '<empty>'}"
        event_time = (event.minute, event.second)
        if not event.id or event.id in seen:
            raise ValueError(f"{label}: event IDs must be nonempty and unique")
        if event_time <= previous_time:
            raise ValueError(f"{label}: events must be in strictly chronological order")
        previous_time = event_time
        if event.team_id not in teams:
            raise ValueError(f"{label}: unknown team_id {event.team_id}")
        if event.possession_team_id not in teams:
            raise ValueError(f"{label}: possession_team_id must identify a fixture team")
        if event.player_id is not None:
            player = players.get(event.player_id)
            if player is None or player.team_id != event.team_id:
                raise ValueError(f"{label}: player_id must identify a player on event team")
        elif event.type != "possession_change":
            raise ValueError(f"{label}: {event.type} requires player_id")

        if event.type == "possession_change":
            if event.related_event_id is not None:
                raise ValueError(f"{label}: only goals may have related_event_id")
            if event.team_id == possession_team_id:
                raise ValueError(f"{label}: possession change must switch teams")
            if event.possession_team_id != event.team_id:
                raise ValueError(f"{label}: possession change must name the gaining team")
            possession_team_id = event.team_id
        elif event.type == "tackle":
            if event.related_event_id is not None:
                raise ValueError(f"{label}: only goals may have related_event_id")
            if event.team_id == possession_team_id:
                raise ValueError(f"{label}: tackle must be by the defending team")
            if event.possession_team_id != possession_team_id:
                raise ValueError(f"{label}: tackle cannot itself change possession")
        else:
            if event.team_id != possession_team_id or event.possession_team_id != possession_team_id:
                raise ValueError(f"{label}: attacking event must belong to possessing team")
            if event.type == "goal":
                shot = seen.get(event.related_event_id)
                if shot is None or shot.type != "shot":
                    raise ValueError(f"{label}: goal must link to an earlier shot")
                if shot.team_id != event.team_id or shot.player_id != event.player_id:
                    raise ValueError(f"{label}: goal team and scorer must match linked shot")
                if shot.outcome != "goal":
                    raise ValueError(f"{label}: linked shot must have outcome 'goal'")
                if event.related_event_id in goal_shot_ids:
                    raise ValueError(f"{label}: linked shot already has a goal")
                goal_shot_ids.add(event.related_event_id)
            elif event.related_event_id is not None:
                raise ValueError(f"{label}: only goals may have related_event_id")
            elif event.type == "shot" and not event.outcome:
                raise ValueError(f"{label}: shot requires outcome")
        seen[event.id] = event

    for event in fixture.events:
        if event.type == "shot" and event.outcome == "goal" and event.id not in goal_shot_ids:
            raise ValueError(f"event {event.id}: goal shot has no linked goal event")


def load_fixture(path: Path | None = None) -> MatchFixture:
    """Load the golden fixture (or a supplied path) and validate it fully."""
    fixture_path = Path(path) if path is not None else DEFAULT_FIXTURE_PATH
    try:
        raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read fixture {fixture_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in fixture {fixture_path}: {exc.msg}") from exc
    try:
        fixture = MatchFixture.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"invalid fixture {fixture_path}: {exc}") from exc
    validate_fixture(fixture)
    return fixture
