"""Evidence-bound wording for the synthetic match, with an optional Foundry adapter.

Set FOUNDRY_RESPONSES_URL to the full v1 /responses endpoint, plus
FOUNDRY_API_KEY and FOUNDRY_MODEL. Without all three, wording uses templates.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any, Literal
from urllib.request import Request, urlopen

from .engine import snapshot_for_minute
from .models import MatchFixture

Mode = Literal["fan", "analyst"]
_NUMBER = re.compile(r"(?<![\w])\d+(?:\.\d+)?%?")
_NUMBER_WORD = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
    r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"first|second|third)\b", re.IGNORECASE
)
_EVENT_REF = re.compile(r"\b(?:e\d{2,}|(?:goal|surge|swing)-[A-Za-z0-9-]+)\b")
_CAPITALIZED = re.compile(r"\b[A-Z][A-Za-z]*(?:'[A-Za-z]+)?\b")
_SAFE_WORDS = {
    "A", "An", "At", "After", "Across", "Based", "Before", "Both", "By",
    "Each", "Event", "Events", "Evidence", "Final", "For", "From", "Full",
    "Goal", "Goals", "In", "It", "Its", "Match", "No", "One", "Only",
    "Passes", "Possession", "Score", "Shots", "Synthetic", "Team", "The",
    "Their", "There", "These", "They", "This", "With", "While",
}
_UNSUPPORTED_CAUSES = re.compile(
    r"\b(?:because|caused|forced|tactics?|press(?:ing|ed)?|injur(?:y|ies)|"
    r"fatigue|confidence|dominance|controlled|outplayed|won|wins?|beat|beats|"
    r"defeat(?:ed|s)?|led|leads?|ahead|behind|equaliz(?:ed|es)|drew)\b",
    re.IGNORECASE,
)
_UNSUPPORTED_COMPARISONS = re.compile(
    r"\b(?:more|fewer|less|higher|lower|most|least|failed|missed|never|without)\b",
    re.IGNORECASE,
)
_WRONG_METRIC = {
    "shot_surge": re.compile(r"\b(?:goal|scor(?:e|ed|ing)|possession|passes?|tackles?)\b", re.IGNORECASE),
    "possession_swing": re.compile(r"\b(?:goal|scor(?:e|ed|ing)|shots?|passes?|tackles?)\b", re.IGNORECASE),
}


def _check_mode(mode: str) -> None:
    if mode not in ("fan", "analyst"):
        raise ValueError("mode must be 'fan' or 'analyst'")


def _team_name(fixture: MatchFixture, team_id: str) -> str:
    return next(team.name for team in fixture.teams if team.id == team_id)


def _player_name(fixture: MatchFixture, player_id: str | None) -> str | None:
    return next((player.name for player in fixture.players if player.id == player_id), None)


def _canonical_insight(fixture: MatchFixture, insight: dict) -> dict:
    insight_id = insight.get("id")
    if not isinstance(insight_id, str):
        raise ValueError("insight needs an engine-generated id")
    for card in snapshot_for_minute(fixture, 90)["insights"]:
        if card["id"] == insight_id:
            return card
    raise ValueError(f"unknown insight id: {insight_id}")


def _evidence(card: dict) -> dict:
    return {
        "type": card["type"],
        "minute": card["minute"],
        "team_id": card["team_id"],
        "event_ids": list(card["evidence_event_ids"]),
        **card["evidence"],
    }


def _insight_template(fixture: MatchFixture, card: dict, mode: Mode) -> str:
    team = _team_name(fixture, card["team_id"])
    facts = card["evidence"]
    if card["type"] == "goal":
        scorer = _player_name(fixture, facts["player_id"])
        before = facts["score_before"]
        after = facts["score_after"]
        score = "–".join(str(after[item.id]) for item in fixture.teams)
        if mode == "fan":
            return f"{team} scored at minute {card['minute']}; the score is {score}."
        prior = "–".join(str(before[item.id]) for item in fixture.teams)
        scorer_text = f" by {scorer}" if scorer else ""
        return (
            f"{team}'s goal{scorer_text} at minute {card['minute']} changed the "
            f"score from {prior} to {score} (events {', '.join(card['evidence_event_ids'])})."
        )
    if card["type"] == "shot_surge":
        other = next(item for item in fixture.teams if item.id != card["team_id"])
        own = facts["shot_counts"][card["team_id"]]
        theirs = facts["shot_counts"][other.id]
        if mode == "fan":
            return f"{team} took {own} shots in the recent window, compared with {theirs} for {other.name}."
        return (
            f"From minutes {facts['window_start_minute_inclusive']}–"
            f"{facts['window_end_minute_inclusive']}, {team} recorded {own} shots "
            f"and {other.name} recorded {theirs} (events {', '.join(card['evidence_event_ids'])})."
        )
    previous = facts["previous_possession_percent"][card["team_id"]]
    current = facts["current_possession_percent"][card["team_id"]]
    if mode == "fan":
        return f"{team}'s measured possession share rose from {previous}% to {current}% across the two recent windows."
    return (
        f"{team}'s possession share rose by {facts['change_points']} percentage points, "
        f"from {previous}% in minutes {facts['previous_window'][0]}–{facts['previous_window'][1]} "
        f"to {current}% in minutes {facts['current_window'][0]}–{facts['current_window'][1]} "
        f"(events {', '.join(card['evidence_event_ids'])})."
    )


def _valid_text(text: Any, names: set[str], references: set[str],
                insight_type: str | None = None) -> bool:
    if not isinstance(text, str) or not text.strip() or len(text) > 500:
        return False
    if _UNSUPPORTED_CAUSES.search(text) or _UNSUPPORTED_COMPARISONS.search(text):
        return False
    if insight_type in _WRONG_METRIC and _WRONG_METRIC[insight_type].search(text):
        return False
    mentioned_refs = set(_EVENT_REF.findall(text))
    if not mentioned_refs <= references:
        return False
    without_refs = _EVENT_REF.sub("", text)
    # A number can be correct but attached to the wrong team or metric. Keep all
    # quantitative wording in the verified evidence and deterministic templates.
    if _NUMBER.search(without_refs) or _NUMBER_WORD.search(without_refs):
        return False
    name_words = {word.casefold() for name in names for word in _CAPITALIZED.findall(name)}
    safe = {word.casefold() for word in _SAFE_WORDS}
    if any(word.casefold() not in name_words | safe for word in _CAPITALIZED.findall(without_refs)):
        return False
    # A capitalized fixture player's name may only be used when that player is evidence.
    return True


def _response_text(response: Any) -> str | None:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return None
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    if isinstance(response.get("text"), str):
        return response["text"]
    pieces = [
        item.get("text")
        for message in response.get("output", [])
        if isinstance(message, dict)
        for item in message.get("content", [])
        if isinstance(item, dict) and item.get("type") == "output_text"
    ]
    return "\n".join(piece for piece in pieces if isinstance(piece, str)) or None


def _foundry_response(payload: dict) -> Any:
    url = os.getenv("FOUNDRY_RESPONSES_URL")
    key = os.getenv("FOUNDRY_API_KEY")
    model = os.getenv("FOUNDRY_MODEL")
    if not all((url, key, model)):
        return None
    request = Request(
        url,
        data=json.dumps({
            "model": model,
            "input": [
                {"role": "system", "content": (
                    "Write only a concise factual explanation of the supplied synthetic match facts. "
                    "Use no numbers, number words, scores, counts, percentages, minutes, "
                    "outcome claims, causes, or tactical claims. For an insight, name only "
                    "the focal team. For a recap, use no team or player names."
                )},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
            "max_output_tokens": 150,
            "store": False,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "api-key": key},
        method="POST",
    )
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def _wording(payload: dict, template: str, names: set[str],
             references: set[str], client: Callable[[dict], Any] | None,
             insight_type: str | None = None) -> tuple[str, str]:
    try:
        response = client(payload) if client is not None else _foundry_response(payload)
        candidate = _response_text(response)
        if _valid_text(candidate, names, references, insight_type):
            return candidate.strip(), "foundry"
    except Exception:
        # The model is optional. Network, parsing, and injected-client failures
        # all leave the replay usable through the deterministic template.
        pass
    return template, "template"


def explain_insight(
    fixture: MatchFixture, insight: dict, mode: Mode, client: Callable[[dict], Any] | None = None
) -> dict:
    """Explain an engine insight; caller-provided evidence cannot replace engine facts."""
    _check_mode(mode)
    card = _canonical_insight(fixture, insight)
    evidence = _evidence(card)
    names = {_team_name(fixture, card["team_id"])}
    player = _player_name(fixture, card["evidence"].get("player_id"))
    if player:
        names.add(player)
    payload = {
        "insight_type": card["type"], "minute": card["minute"], "mode": mode,
        "verified_facts": evidence, "evidence_event_ids": card["evidence_event_ids"],
        "team_names": {team.id: team.name for team in fixture.teams},
        "supported_player_name": player,
    }
    text, source = _wording(payload, _insight_template(fixture, card, mode),
                            names, set(card["evidence_event_ids"]), client, card["type"])
    return {"insight_id": card["id"], "mode": mode, "text": text,
            "evidence": evidence, "source": source}


def build_recap(
    fixture: MatchFixture, mode: Mode, client: Callable[[dict], Any] | None = None
) -> dict:
    """Build a full-time recap from the final engine snapshot and goal moments."""
    _check_mode(mode)
    final = snapshot_for_minute(fixture, 90)
    goals = [card for card in final["insights"] if card["type"] == "goal"]
    moment_ids = [card["id"] for card in goals]
    first, second = fixture.teams
    score = final["score"]
    stats = final["stats"]
    if mode == "fan":
        template = (
            f"At full time, {first.name} {score[first.id]}–{score[second.id]} {second.name}. "
            f"The event record shows {len(goals)} goals and {stats['shots'][first.id]}–"
            f"{stats['shots'][second.id]} shots."
        )
    else:
        template = (
            f"Final score: {first.name} {score[first.id]}–{score[second.id]} {second.name}. "
            f"Event-derived totals: shots {stats['shots'][first.id]}–{stats['shots'][second.id]}, "
            f"passes {stats['passes'][first.id]}–{stats['passes'][second.id]}, and "
            f"possession {stats['possession_percent'][first.id]}%–"
            f"{stats['possession_percent'][second.id]}%. "
            f"The {len(goals)} goal events are {', '.join(moment_ids) if goals else 'none'}."
        )
    if not fixture.events:
        template += " Evidence is limited: the fixture contains no events."
    references = set(moment_ids)
    for card in goals:
        references.update(card["evidence_event_ids"])
    facts = {"final_score": score, "stats": stats,
             "goal_count": len(goals), "goal_minutes": [card["minute"] for card in goals]}
    payload = {"mode": mode, "verified_facts": facts, "moment_ids": moment_ids,
               "evidence_event_ids": sorted(references - set(moment_ids)),
               "team_names": {team.id: team.name for team in fixture.teams}}
    text, source = _wording(payload, template, set(), references, client)
    return {"mode": mode, "text": text, "final_score": score,
            "stats": stats, "moment_ids": moment_ids, "source": source}
