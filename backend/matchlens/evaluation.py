"""Offline, evidence-bound AI evaluation with explicit provenance.

Injected client checks exercise the actual generation boundary but are not live
Foundry quality measurements. The golden fixture is never modified.
"""
from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from .engine import snapshot_for_minute
from .fixture import load_fixture, validate_fixture
from .models import MatchEvent, MatchFixture

CORPUS_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai_cases.json"


def fixture_for_scenario(name: str) -> MatchFixture:
    """Return an independently validated fictional fixture for one scenario."""
    fixture = load_fixture().model_copy(deep=True)
    if name == "golden":
        return fixture
    fixture.match_id = "evaluation-" + name
    fixture.fixture_version = "evaluation-1-" + name
    fixture.events = []
    if name == "empty":
        validate_fixture(fixture)
        return fixture
    schedules = {
        "draw": [(12, "blue"), (57, "red")],
        "comeback": [(12, "red"), (57, "blue"), (84, "blue")],
        "late_winner": [(90, "blue")],
        "extended_lead": [(12, "blue"), (30, "blue")],
        "reduced_deficit": [(12, "red"), (30, "red"), (57, "blue")],
        "goalless": [],
    }
    if name not in schedules:
        raise ValueError("unknown evaluation scenario")
    holder = fixture.initial_possession_team_id
    events = []
    for index, (minute, team_id) in enumerate(schedules[name]):
        player = next(p.id for p in fixture.players if p.team_id == team_id)
        if holder != team_id:
            events.append(MatchEvent(id=f"eval-switch-{index}", minute=minute,
                                     second=0, type="possession_change", team_id=team_id,
                                     possession_team_id=team_id))
            holder = team_id
        shot_id = f"eval-shot-{index}"
        events.extend([
            MatchEvent(id=shot_id, minute=minute, second=5, type="shot", team_id=team_id,
                       player_id=player, outcome="goal", possession_team_id=holder),
            MatchEvent(id=f"eval-goal-{index}", minute=minute, second=6, type="goal",
                       team_id=team_id, player_id=player, possession_team_id=holder,
                       related_event_id=shot_id),
        ])
    if name == "goalless":
        player = next(p.id for p in fixture.players if p.team_id == holder)
        events = [MatchEvent(id="eval-pass", minute=1, second=1, type="pass", team_id=holder,
                            player_id=player, outcome="completed", possession_team_id=holder),
                  MatchEvent(id="eval-saved", minute=10, second=1, type="shot", team_id=holder,
                             player_id=player, outcome="saved", possession_team_id=holder)]
    fixture.events = events
    validate_fixture(fixture)
    return fixture


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    raw = json.loads((path or CORPUS_PATH).read_text(encoding="utf-8"))
    if raw.get("schema_version") != "1.0" or not isinstance(raw.get("cases"), list):
        raise ValueError("unsupported AI evaluation corpus")
    cases = raw["cases"]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)) or not all(ids):
        raise ValueError("evaluation case IDs must be unique")
    if any(case.get("category") not in {"snapshot", "context", "generation", "recap"} for case in cases):
        raise ValueError("unknown evaluation category")
    return cases


def _source(result: Any) -> str | None:
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    if not isinstance(result, dict):
        return None
    metadata = result.get("metadata", {})
    if hasattr(metadata, "model_dump"):
        metadata = metadata.model_dump(mode="json")
    return result.get("source") or metadata.get("source")


def _dictionary(result: Any) -> dict:
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else result


def _goal(fixture: MatchFixture, index: int = 0) -> dict:
    return [i for i in snapshot_for_minute(fixture, 90)["insights"] if i["type"] == "goal"][index]


def _packet(case: dict, fixture: MatchFixture):
    from .context import build_context
    final = snapshot_for_minute(fixture, 90)
    if "insight_type" in case:
        insight = next(i for i in final["insights"] if i["type"] == case["insight_type"])
    else:
        insight = _goal(fixture, case.get("goal_index", 0))
    return build_context(fixture, insight["id"], case.get("as_of_minute", insight["minute"]))


def _valid_selection(packet) -> dict:
    return {"selected_fact_ids": [fact.id for fact in packet.facts],
            "interpretation_code": packet.supported_interpretations[0],
            "fan_frame": "contextual", "analyst_frame": "comparison", "limitations": []}


def _snapshot_check(case: dict, fixture: MatchFixture) -> None:
    snapshot = snapshot_for_minute(fixture, case.get("minute", 90))
    check = case["check"]
    if check in {"score", "shots", "passes", "possession"}:
        actual = snapshot["score"] if check == "score" else snapshot["stats"]["possession_percent" if check == "possession" else check]
        assert actual == case["expected"], f"{check}: expected {case['expected']}, got {actual}"
    elif check == "goal_count":
        assert sum(i["type"] == "goal" for i in snapshot["insights"]) == case["expected"]
    elif check == "future_exclusion":
        assert all(e["minute"] <= snapshot["minute"] for e in snapshot["recent_events"])
        assert all(i["minute"] <= snapshot["minute"] for i in snapshot["insights"])
        assert snapshot["score"] == case["expected"]
    elif check == "window":
        assert all(snapshot["minute"] - 10 < e["minute"] <= snapshot["minute"] for e in snapshot["recent_events"])
        assert snapshot["recent_events"], "golden window unexpectedly empty"
    elif check == "shot_goal_once":
        assert snapshot["stats"]["shots"] == snapshot["score"] == case["expected"]
    elif check == "deterministic":
        snapshot_for_minute(fixture, 0)
        assert snapshot == snapshot_for_minute(fixture, snapshot["minute"])
    elif check == "empty_stats":
        assert snapshot["stats"]["shots"] == snapshot["stats"]["passes"] == {"blue": 0, "red": 0}
        assert snapshot["insights"] == snapshot["recent_events"] == []
    elif check == "possession_sum":
        assert sum(snapshot["stats"]["possession_percent"].values()) == 100
    else:
        raise ValueError("unknown snapshot check: " + check)


def _context_check(case: dict, fixture: MatchFixture) -> None:
    from .context import build_context
    check = case["check"]
    if check in {"reject_future", "reject_unknown"}:
        insight_id = "missing-insight" if check == "reject_unknown" else _goal(fixture)["id"]
        try:
            build_context(fixture, insight_id, 0)
        except (ValueError, KeyError):
            return
        raise AssertionError("unknown or future insight was accepted")
    packet = _packet(case, fixture)
    if check == "interpretation":
        assert case["expected"] in packet.supported_interpretations, str(packet.supported_interpretations)
    elif check == "no_future_evidence":
        event_ids = set(packet.evidence_event_ids)
        assert event_ids <= {e.id for e in fixture.events if e.minute <= packet.as_of_minute}
    elif check == "unique_facts":
        assert packet.facts and len({fact.id for fact in packet.facts}) == len(packet.facts)
    elif check == "limitations":
        assert packet.limitations, "unsupported tracking/tactical certainty must be limited"
    elif check == "stable":
        assert packet == _packet(case, fixture)
    elif check == "linked_shot":
        goal = _goal(fixture, case.get("goal_index", 0))
        assert set(goal["evidence_event_ids"]) <= set(packet.evidence_event_ids)
    else:
        raise ValueError("unknown context check: " + check)


def _generation_check(case: dict, fixture: MatchFixture, adapter: Callable | None) -> None:
    if adapter is None:
        from .narrative import generate_narrative
        adapter = generate_narrative
    packet = _packet(case, fixture)
    candidate = _valid_selection(packet)
    check = case["check"]
    if check == "valid":
        result = adapter(packet, client=lambda _payload: candidate)
        assert _dictionary(result).get("selection_accepted") is True, "valid injected selection was rejected"
        assert _source(result) == "template", "injected client must not claim live Foundry"
        assert _dictionary(result).get("selection_source") == "injected"
        return
    if check == "paired_modes":
        result = _dictionary(adapter(packet, client=lambda _payload: candidate))
        narrative = _dictionary(result.get("narrative", result))
        assert narrative["fan_explanation"] and narrative["analyst_explanation"]
        assert narrative["fan_explanation"] != narrative["analyst_explanation"]
        assert set(narrative["selected_fact_ids"]) <= {f.id for f in packet.facts}
        return
    if check == "timeout":
        def client(_payload):
            raise TimeoutError("synthetic evaluation timeout")
    elif check == "connection_failure":
        def client(_payload):
            raise ConnectionError("synthetic evaluation network failure")
    else:
        if check == "unknown_fact": candidate["selected_fact_ids"] = ["invented-fact"]
        elif check == "duplicate_fact": candidate["selected_fact_ids"] *= 2
        elif check == "empty_facts": candidate["selected_fact_ids"] = []
        elif check == "wrong_interpretation": candidate["interpretation_code"] = "POSSESSION_INCREASE"
        elif check == "future_fact": candidate["selected_fact_ids"] = ["future-goal-at-84"]
        elif check == "fan_frame": candidate["fan_frame"] = "invented"
        elif check == "analyst_frame": candidate["analyst_frame"] = "invented"
        elif check == "limitation": candidate["limitations"] = ["A fictional unsupported limitation"]
        elif check == "extra_field": candidate["fan_explanation"] = "Northstar Quay did not score."
        elif check == "refusal": candidate = {"refusal": "synthetic test refusal"}
        elif check == "empty": candidate = None
        elif check == "malformed": candidate = "{not valid JSON"
        elif check == "wrong_shape": candidate = ["not", "an", "object"]
        elif check in {"negated_goal", "reversed_score", "invented_player", "tactics", "future_prose"}:
            candidate = case["candidate"]
        else:
            raise ValueError("unknown generation check: " + check)
        def client(_payload):
            return deepcopy(candidate)
    result = adapter(packet, client=client)
    assert _source(result) == "template", f"unsafe/failed {check} did not fall back"
    assert _dictionary(result).get("selection_accepted") is False, f"unsafe {check} was accepted"


def _recap_check(case: dict, fixture: MatchFixture) -> None:
    from .story import build_recap_context, build_story
    packet = build_recap_context(fixture)
    check = case["check"]
    assert packet.as_of_minute == 90
    if check == "limited":
        assert packet.limitations
    elif check == "facts":
        values = [f.value for f in packet.facts]
        score = snapshot_for_minute(fixture, 90)["score"]
        # Score facts may be represented as a pair or as one typed fact per team.
        assert score in values or all(any(f.team_id == team and f.value == value and "score" in f.metric for f in packet.facts) for team, value in score.items())
    elif check == "story_evidence":
        story = _dictionary(build_story(fixture, as_of_minute=90))
        assert story
        assert set(packet.evidence_event_ids) <= {e.id for e in fixture.events}
    elif check == "story_no_future":
        story = _dictionary(build_story(fixture, as_of_minute=20))
        text = json.dumps(story, default=lambda obj: obj.model_dump(mode="json"))
        for event in fixture.events:
            if event.minute > 20:
                assert f'"{event.id}"' not in text
    else:
        raise ValueError("unknown recap check: " + check)


def run_case(case: dict, *, generation_adapter: Callable | None = None) -> dict:
    started = perf_counter()
    try:
        fixture = fixture_for_scenario(case.get("scenario", "golden"))
        category = case["category"]
        if category == "snapshot": _snapshot_check(case, fixture)
        elif category == "context": _context_check(case, fixture)
        elif category == "generation": _generation_check(case, fixture, generation_adapter)
        elif category == "recap": _recap_check(case, fixture)
        else: raise ValueError("unknown category")
        status, error = "passed", None
    except Exception as exc:
        status, error = "failed", f"{type(exc).__name__}: {str(exc)[:300]}"
    return {"id": case["id"], "category": case["category"], "status": status,
            "error": error, "duration_ms": round((perf_counter() - started) * 1000, 3),
            "provenance": "injected_client" if case["category"] == "generation" else "deterministic"}


def run_evaluation(cases: list[dict] | None = None, *, generation_adapter: Callable | None = None) -> dict:
    selected = cases if cases is not None else load_cases()
    results = [run_case(case, generation_adapter=generation_adapter) for case in selected]
    counts = Counter(result["status"] for result in results)
    return {"schema_version": "1.0", "mode": "offline", "synthetic": True,
            "total": len(results), "passed": counts["passed"], "failed": counts["failed"],
            "categories": dict(Counter(case["category"] for case in selected)),
            "live_model_metrics": {"status": "not_measured", "latency_ms": None,
                                   "token_usage": None, "factual_error_rate": None},
            "human_usefulness": {"status": "pending_human_review", "score": None},
            "results": results}
