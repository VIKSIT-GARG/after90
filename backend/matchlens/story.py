"""Deterministic story selection for the wholly synthetic match.

The ledger is facts, not generated prose. It groups overlapping same-team pattern
windows and preserves every goal. Recaps may use final results; a live ledger
never inspects events after its requested minute.
"""

from __future__ import annotations

from typing import TypedDict

from .ai_schemas import ContextPacket, Fact, InclusiveWindow
from .engine import snapshot_for_minute
from .fixture import validate_fixture
from .models import MatchFixture


class StoryMoment(TypedDict):
    id: str
    type: str
    minute: int
    team_id: str
    interpretation_code: str
    evidence_event_ids: list[str]
    member_insight_ids: list[str]
    window: list[int]
    group_window: list[int]
    significance: int
    winning_goal: bool
    evidence: dict


class StoryLedger(TypedDict):
    match_id: str
    fixture_version: str
    as_of_minute: int
    synthetic: bool
    moments: list[StoryMoment]
    all_moments: list[StoryMoment]
    omitted_moment_ids: list[str]
    limitations: list[str]


_LIMITATIONS = [
    "Synthetic event data; interpretations describe recorded events only.",
    "Shot volume does not establish chance quality, tactical pressure or dominance.",
    "No tracking, speed, injury or tactical-cause evidence is available.",
]


def _window(card: dict) -> list[int]:
    evidence = card["evidence"]
    if card["type"] == "shot_surge":
        return [evidence["window_start_minute_inclusive"], evidence["window_end_minute_inclusive"]]
    if card["type"] == "possession_swing":
        return [evidence["previous_window"][0], evidence["current_window"][1]]
    return [card["minute"], card["minute"]]


def _rank(card: dict, interpretation: str) -> int:
    if card["type"] == "goal":
        context_bonus = {"GOAL_EQUALIZES": 20, "GOAL_TAKES_LEAD": 25,
                         "GOAL_OPENS_SCORING": 15}.get(interpretation, 5)
        return 100 + context_bonus + (10 if card["minute"] >= 75 else 0)
    if card["type"] == "shot_surge":
        counts = card["evidence"]["shot_counts"]
        focal = counts[card["team_id"]]
        other = next(value for team, value in counts.items() if team != card["team_id"])
        return 65 + min(10, focal - other)
    return 45 + min(10, card["evidence"]["change_points"] // 5)


def _ordered_ids(ids: set[str], fixture: MatchFixture) -> list[str]:
    return [event.id for event in fixture.events if event.id in ids]


def _deduplicate(patterns: list[StoryMoment], fixture: MatchFixture) -> list[StoryMoment]:
    """Merge connected overlapping windows by team/type, retaining all evidence.

    A strongest representative supplies the explanation facts; member IDs retain
    every original insight, so grouping does not silently discard provenance.
    ``window`` and ``evidence`` always describe the representative only;
    ``group_window`` is union coverage, never the representative metric window.
    """
    groups: list[list[StoryMoment]] = []
    for moment in sorted(patterns, key=lambda item: (item["window"][0], item["minute"], item["id"])):
        matching = [group for group in groups if group[0]["type"] == moment["type"]
                    and group[0]["team_id"] == moment["team_id"]
                    and min(item["window"][0] for item in group) <= moment["window"][1]
                    and max(item["window"][1] for item in group) >= moment["window"][0]]
        if not matching:
            groups.append([moment])
            continue
        combined = [moment]
        for group in matching:
            combined.extend(group)
            groups.remove(group)
        groups.append(combined)
    result: list[StoryMoment] = []
    for group in groups:
        representative = min(group, key=lambda item: (-item["significance"], item["minute"], item["id"]))
        combined: StoryMoment = {
            **representative,
            "group_window": [min(item["window"][0] for item in group), max(item["window"][1] for item in group)],
            "member_insight_ids": [item["id"] for item in sorted(group, key=lambda item: (item["minute"], item["id"]))],
            "evidence_event_ids": _ordered_ids({ref for item in group for ref in item["evidence_event_ids"]}, fixture),
        }
        result.append(combined)
    return result


def build_story(fixture: MatchFixture, as_of_minute: int = 90, *, max_moments: int = 6) -> StoryLedger:
    """Build a canonical story as of a minute, without reading future match facts.

    ``max_moments`` bounds non-goal selection, not the goal count: every goal is
    preserved even when there are more goals than the requested presentation cap.
    Output order is chronological; ranking only chooses which patterns to show.
    """
    from .context import build_context

    validate_fixture(fixture)
    if isinstance(max_moments, bool) or not isinstance(max_moments, int) or max_moments < 1:
        raise ValueError("max_moments must be a positive integer")
    snapshot = snapshot_for_minute(fixture, as_of_minute)
    cards = snapshot["insights"]
    moments: list[StoryMoment] = []
    for card in cards:
        packet = build_context(fixture, card["id"], as_of_minute)
        interpretation = packet.supported_interpretations[0]
        moments.append({
            "id": card["id"], "type": card["type"], "minute": card["minute"],
            "team_id": card["team_id"], "interpretation_code": interpretation,
            "evidence_event_ids": _ordered_ids(set(card["evidence_event_ids"]), fixture),
            "member_insight_ids": [card["id"]], "window": _window(card), "group_window": _window(card),
            "significance": _rank(card, interpretation), "winning_goal": False,
            "evidence": card["evidence"],
        })
    goals = [item for item in moments if item["type"] == "goal"]
    if as_of_minute == 90:
        score = snapshot["score"]
        winner = max(score, key=score.get)
        opponent = next(team for team in score if team != winner)
        if score[winner] > score[opponent]:
            winning_count = score[opponent] + 1
            for goal in goals:
                if goal["team_id"] == winner and goal["evidence"]["score_after"][winner] == winning_count:
                    goal["winning_goal"] = True
                    break
    patterns = _deduplicate([item for item in moments if item["type"] != "goal"], fixture)
    ranked = sorted(patterns, key=lambda item: (-item["significance"], item["minute"], item["id"]))
    selected = list(goals)
    remaining = max(0, max_moments - len(goals))
    # Represent distinct observed pattern types before filling extra slots.
    for kind in ("shot_surge", "possession_swing"):
        candidate = next((item for item in ranked if item["type"] == kind), None)
        if candidate is not None and remaining:
            selected.append(candidate)
            remaining -= 1
    selected_ids = {item["id"] for item in selected}
    for item in ranked:
        if remaining and item["id"] not in selected_ids:
            selected.append(item)
            selected_ids.add(item["id"])
            remaining -= 1
    chronological = lambda item: (item["minute"], item["id"])
    all_moments = sorted(goals + patterns, key=chronological)
    selected.sort(key=chronological)
    selected_ids = {item["id"] for item in selected}
    limitations = list(_LIMITATIONS)
    if not any(event.minute <= as_of_minute for event in fixture.events):
        limitations.append("Evidence is limited: no events are recorded at or before this minute.")
    elif not cards:
        limitations.append("No recorded pattern meets the configured insight thresholds.")
    return {
        "match_id": fixture.match_id, "fixture_version": fixture.fixture_version,
        "as_of_minute": as_of_minute, "synthetic": True, "moments": selected,
        "all_moments": all_moments,
        "omitted_moment_ids": [item["id"] for item in all_moments if item["id"] not in selected_ids],
        "limitations": limitations,
    }


def build_recap_context(fixture: MatchFixture) -> ContextPacket:
    """Build a full-time packet including goals and selected non-goal patterns."""
    ledger = build_story(fixture, 90)
    final = snapshot_for_minute(fixture, 90)
    window = InclusiveWindow(start=0, end=90)
    facts = [Fact(id="final_score", metric="score", value=final["score"], window=window)]
    for team in fixture.teams:
        for prefix, metric, stats_key, unit in [
            ("shots", "shot_count", "shots", "shots"),
            ("passes", "pass_count", "passes", "passes"),
            ("possession", "possession_percent", "possession_percent", "%"),
        ]:
            facts.append(Fact(id=f"{prefix}_{team.id}", metric=metric,
                              value=final["stats"][stats_key][team.id], team_id=team.id,
                              unit=unit, window=window))
    facts.extend([
        Fact(id="selected_moment_ids", metric="moment_ids", value=[item["id"] for item in ledger["moments"]]),
        Fact(id="goal_minutes", metric="goal_minutes", value=[item["minute"] for item in ledger["all_moments"] if item["type"] == "goal"]),
        Fact(id="story_summary", metric="story_moments", value=[dict(item) for item in ledger["moments"]]),
    ])
    interpretations = ["MATCH_RECAP"]
    if not fixture.events:
        interpretations.append("LIMITED_EVIDENCE")
    return ContextPacket(
        match_id=fixture.match_id, fixture_version=fixture.fixture_version,
        insight_id=f"recap-{fixture.fixture_version}", insight_type="recap", minute=90,
        as_of_minute=90, team_id=None, teams={team.id: team.name for team in fixture.teams},
        facts=facts,
        evidence_event_ids=_ordered_ids({ref for moment in ledger["moments"] for ref in moment["evidence_event_ids"]}, fixture),
        supported_interpretations=interpretations, limitations=ledger["limitations"],
    )
