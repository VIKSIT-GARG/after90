"""Pure, deterministic replay calculations for a synthetic fixture."""

from __future__ import annotations

from collections import Counter

from .models import MatchEvent, MatchFixture


def _ordered_events(fixture: MatchFixture) -> list[MatchEvent]:
    # A fixture may arrive in file order; timestamps, then that order, define ties.
    return sorted(fixture.events, key=lambda event: (event.minute, event.second))


def _possession_seconds(
    fixture: MatchFixture, changes: list[MatchEvent], start: int, end: int
) -> dict[str, int]:
    """Allocate a half-open clock interval using the explicit initial holder."""
    seconds = {team.id: 0 for team in fixture.teams}
    holder = fixture.initial_possession_team_id
    cursor = start
    for event in changes:
        at = event.minute * 60 + event.second
        if at <= start:
            holder = event.possession_team_id  # type: ignore[assignment]
        elif at < end:
            seconds[holder] += at - cursor
            cursor = at
            holder = event.possession_team_id  # type: ignore[assignment]
        else:
            break
    seconds[holder] += end - cursor
    return seconds


def _percent(seconds: dict[str, int], team_ids: list[str]) -> dict[str, int]:
    total = sum(seconds.values())
    if total == 0:
        return {team_ids[0]: 50, team_ids[1]: 50}
    first = (seconds[team_ids[0]] * 100 + total // 2) // total
    return {team_ids[0]: first, team_ids[1]: 100 - first}


def _possession_percent(
    fixture: MatchFixture, changes: list[MatchEvent], start: int, end: int
) -> dict[str, int]:
    return _percent(
        _possession_seconds(fixture, changes, start, end),
        [team.id for team in fixture.teams],
    )


def _insights(
    fixture: MatchFixture, ordered: list[MatchEvent], minute: int
) -> list[dict]:
    team_ids = [team.id for team in fixture.teams]
    changes = [event for event in ordered if event.type == "possession_change"]
    cards: list[dict] = []
    score = dict.fromkeys(team_ids, 0)
    previous_surge: set[str] = set()
    previous_swing: set[str] = set()

    for current in range(minute + 1):
        for event in ordered:
            if event.minute != current or event.type != "goal":
                continue
            before = score.copy()
            score[event.team_id] += 1
            evidence_ids = [event.id]
            if event.related_event_id is not None:
                evidence_ids.append(event.related_event_id)
            cards.append(
                {
                    "id": f"goal-{event.id}",
                    "type": "goal",
                    "minute": current,
                    "team_id": event.team_id,
                    "evidence_event_ids": evidence_ids,
                    "evidence": {
                        "goal_event_id": event.id,
                        "shot_event_id": event.related_event_id,
                        "player_id": event.player_id,
                        "score_before": before,
                        "score_after": score.copy(),
                    },
                }
            )

        window_shots = [
            event
            for event in ordered
            if event.type == "shot" and current - 10 < event.minute <= current
        ]
        shot_counts = Counter(event.team_id for event in window_shots)
        active_surge = {
            team_id
            for team_id in team_ids
            if shot_counts[team_id] >= 3
            and all(
                shot_counts[team_id] - shot_counts[other] >= 2
                for other in team_ids
                if other != team_id
            )
        }
        for team_id in team_ids:
            if team_id in active_surge and team_id not in previous_surge:
                cards.append(
                    {
                        "id": f"surge-{current}-{team_id}",
                        "type": "shot_surge",
                        "minute": current,
                        "team_id": team_id,
                        "evidence_event_ids": [event.id for event in window_shots],
                        "evidence": {
                            "window_start_minute_inclusive": max(0, current - 9),
                            "window_end_minute_inclusive": current,
                            "shot_counts": {
                                candidate: shot_counts[candidate]
                                for candidate in team_ids
                            },
                        },
                    }
                )
        previous_surge = active_surge

        # Two complete, adjacent 10-minute windows are available from minute 19.
        active_swing: set[str] = set()
        if current >= 19:
            previous_start = (current - 19) * 60
            midpoint = (current - 9) * 60
            current_end = (current + 1) * 60
            previous_changes = [
                event
                for event in changes
                if previous_start <= event.minute * 60 + event.second < midpoint
            ]
            current_changes = [
                event
                for event in changes
                if midpoint <= event.minute * 60 + event.second < current_end
            ]
            # A timed change in each window is the minimum support for a swing.
            if previous_changes and current_changes:
                previous_share = _possession_percent(
                    fixture, changes, previous_start, midpoint
                )
                current_share = _possession_percent(
                    fixture, changes, midpoint, current_end
                )
                active_swing = {
                    team_id
                    for team_id in team_ids
                    if current_share[team_id] - previous_share[team_id] >= 30
                }
                for team_id in team_ids:
                    if team_id in active_swing and team_id not in previous_swing:
                        cards.append(
                            {
                                "id": f"swing-{current}-{team_id}",
                                "type": "possession_swing",
                                "minute": current,
                                "team_id": team_id,
                                "evidence_event_ids": [
                                    event.id
                                    for event in previous_changes + current_changes
                                ],
                                "evidence": {
                                    "previous_window": [current - 19, current - 10],
                                    "current_window": [current - 9, current],
                                    "previous_possession_percent": previous_share,
                                    "current_possession_percent": current_share,
                                    "change_points": (
                                        current_share[team_id]
                                        - previous_share[team_id]
                                    ),
                                    "initial_possession_team_id": (
                                        fixture.initial_possession_team_id
                                    ),
                                },
                            }
                        )
        previous_swing = active_swing

    return cards


def snapshot_for_minute(fixture: MatchFixture, minute: int) -> dict:
    """Return an event-derived snapshot for an inclusive match minute 0 through 90."""
    if isinstance(minute, bool) or not isinstance(minute, int) or not 0 <= minute <= 90:
        raise ValueError("minute must be an integer from 0 through 90")

    ordered = _ordered_events(fixture)
    visible = [event for event in ordered if event.minute <= minute]
    team_ids = [team.id for team in fixture.teams]
    changes = [event for event in visible if event.type == "possession_change"]
    return {
        "match_id": fixture.match_id,
        "fixture_version": fixture.fixture_version,
        "synthetic": fixture.synthetic,
        "minute": minute,
        "teams": [team.model_dump() for team in fixture.teams],
        "score": {
            team_id: sum(
                event.type == "goal" and event.team_id == team_id for event in visible
            )
            for team_id in team_ids
        },
        "stats": {
            "shots": {
                team_id: sum(
                    event.type == "shot" and event.team_id == team_id
                    for event in visible
                )
                for team_id in team_ids
            },
            "passes": {
                team_id: sum(
                    event.type == "pass" and event.team_id == team_id
                    for event in visible
                )
                for team_id in team_ids
            },
            "possession_percent": _possession_percent(
                fixture, changes, 0, (minute + 1) * 60
            ),
        },
        "recent_events": [
            event.model_dump()
            for event in visible
            if event.minute > minute - 10
        ],
        "insights": _insights(fixture, visible, minute),
    }
