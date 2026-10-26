"""Bounded Foundry narrative planning with deterministic evidence rendering.

Foundry selects facts, interpretation and audience frames. It never authors the
factual sentences: the server renders them from the canonical context. Injected
clients are labelled as test provenance and never establish live Foundry use.
This module is not wired into legacy endpoints until delivery phase 7.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .ai_schemas import ContextPacket, GenerationMetadata, NarrativeOutput, NarrativeSelection, NarrativeResult
from .validation import validate_selection

PROMPT_VERSION = "after90-bounded-1"
TIMEOUT_SECONDS = 3
MAX_RESPONSE_BYTES = 64 * 1024
AZURE_HOST_SUFFIXES = (".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class GenerationFailure(ValueError):
    """Public reason codes contain no endpoint, key or raw service response."""


def _endpoint_allowed(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(url.scheme == "https" and url.hostname
                    and any(url.hostname.endswith(suffix) for suffix in AZURE_HOST_SUFFIXES)
                    and url.port in (None, 443) and url.username is None and url.password is None
                    and url.path == "/openai/v1/responses" and not url.query and not url.fragment)
    except (ValueError, TypeError):
        return False


def selection_schema(packet: ContextPacket) -> dict:
    """Narrow every selectable factual reference to this request's packet."""
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "selected_fact_ids": {"type": "array", "items": {"type": "string", "enum": [fact.id for fact in packet.facts]}},
            "interpretation_code": {"type": "string", "enum": list(packet.supported_interpretations)},
            "fan_frame": {"type": "string", "enum": ["concise", "contextual"]},
            "analyst_frame": {"type": "string", "enum": ["evidence", "comparison"]},
            # With no limitations, only [] validates against the packet. A
            # nonempty enum keeps the Azure schema valid; the sentinel is never accepted.
            "limitations": {"type": "array", "items": {"type": "string", "enum": packet.limitations or ["__none__"]}},
        },
        "required": ["selected_fact_ids", "interpretation_code", "fan_frame", "analyst_frame", "limitations"],
    }


def _payload(packet: ContextPacket) -> dict:
    return {"context": packet.model_dump(mode="json"), "response_schema": selection_schema(packet)}


def _call_foundry(payload: dict) -> Any:
    url, key, model = (os.getenv(name, "").strip() for name in ("FOUNDRY_RESPONSES_URL", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"))
    if not all((url, key, model)):
        raise GenerationFailure("not_configured")
    if not _endpoint_allowed(url):
        raise GenerationFailure("invalid_endpoint")
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": (
                "Plan a concise explanation of synthetic football facts using only the supplied selection schema. "
                "Choose a supported interpretation and supporting fact IDs. Select score_before and score_after for goals, "
                "both teams' shot facts for a shot surge, and previous/current/delta focal-team facts for possession. "
                "For recaps retain final_score, selected_moment_ids, story_summary and goal_minutes; any statistical "
                "comparison must retain both teams. Use contextual/comparison framing when the evidence benefits "
                "from detail. Never return prose, new facts, numbers, entities, tactical causes or future events."
            )},
            {"role": "user", "content": json.dumps(payload["context"], sort_keys=True)},
        ],
        "text": {"format": {"type": "json_schema", "name": "after90_narrative_selection", "strict": True, "schema": payload["response_schema"]}},
        "max_output_tokens": 800,
        "store": False,
    }
    request = Request(url, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json", "api-key": key}, method="POST")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GenerationFailure("response_too_large")
        return json.loads(raw)
    except GenerationFailure:
        raise
    except TimeoutError as exc:
        raise GenerationFailure("timeout") from exc
    except HTTPError as exc:
        raise GenerationFailure("http_error") from exc
    except URLError as exc:
        raise GenerationFailure("timeout" if isinstance(exc.reason, TimeoutError) else "transport_error") from exc
    except (ValueError, UnicodeError) as exc:
        raise GenerationFailure("malformed_response") from exc
    except OSError as exc:
        raise GenerationFailure("transport_error") from exc


def _selection_value(response: Any) -> Any:
    if isinstance(response, NarrativeSelection):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        if response.get("status") in ("incomplete", "failed", "cancelled", "in_progress", "queued"):
            raise GenerationFailure("incomplete_response")
        if response.get("error") or response.get("refusal"):
            raise GenerationFailure("model_refusal")
        if "selected_fact_ids" in response:
            return response
        text = response.get("output_text")
        if not isinstance(text, str):
            parts = []
            output = response.get("output", [])
            if not isinstance(output, list):
                raise GenerationFailure("malformed_response")
            for message in output:
                if not isinstance(message, dict):
                    raise GenerationFailure("malformed_response")
                if message.get("status") in ("incomplete", "failed"):
                    raise GenerationFailure("incomplete_response")
                for content in message.get("content", []):
                    if not isinstance(content, dict):
                        raise GenerationFailure("malformed_response")
                    if content.get("type") == "refusal":
                        raise GenerationFailure("model_refusal")
                    if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                        parts.append(content["text"])
            text = "".join(parts)
    elif isinstance(response, str):
        text = response
    else:
        raise GenerationFailure("malformed_response")
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise GenerationFailure("malformed_response") from exc


def fallback_selection(packet: ContextPacket) -> NarrativeSelection:
    return NarrativeSelection(selected_fact_ids=[fact.id for fact in packet.facts],
                              interpretation_code=packet.supported_interpretations[0],
                              fan_frame="contextual", analyst_frame="comparison", limitations=list(packet.limitations))


def _score(value: Any, teams: dict[str, str]) -> str:
    if not isinstance(value, dict) or set(value) != set(teams) or any(type(n) is not int or n < 0 for n in value.values()):
        raise ValueError("score fact must map every team to a nonnegative integer")
    return "–".join(str(value[team]) for team in teams)


def render_narrative(packet: ContextPacket, selection: NarrativeSelection) -> NarrativeOutput:
    """Render factual text exclusively from selected canonical facts."""
    selection = validate_selection(selection.model_dump(mode="json"), packet)
    facts = {fact.id: fact for fact in packet.facts if fact.id in selection.selected_fact_ids}
    team = packet.teams.get(packet.team_id or "", "The focal team")
    code = selection.interpretation_code
    headline = "Recorded match insight"
    fan = analyst = ""
    if packet.insight_type == "goal":
        before, after = _score(facts["score_before"].value, packet.teams), _score(facts["score_after"].value, packet.teams)
        descriptions = {
            "GOAL_OPENS_SCORING": ("The opening goal", "opened the scoring"),
            "GOAL_EQUALIZES": ("Back level", "equalized"),
            "GOAL_TAKES_LEAD": ("A change in the lead", "took the lead"),
            "GOAL_EXTENDS_LEAD": ("The lead grows", "extended their lead"),
            "GOAL_REDUCES_DEFICIT": ("The gap narrows", "reduced their deficit"),
            "GOAL_RECORDED": ("A recorded goal", "scored"),
        }
        headline, action = descriptions.get(code, ("A recorded goal", "scored"))
        fan = f"{team} {action}."
        if selection.fan_frame == "contextual":
            fan += f" The score changed from {before} to {after}."
        scorer = facts.get("scorer_name")
        scorer_text = f" by {scorer.value}" if scorer else ""
        analyst = f"At minute {packet.minute}, {team}'s goal{scorer_text} changed the score from {before} to {after}."
        if selection.analyst_frame == "comparison":
            analyst += f" This event means {team} {action}."
    elif packet.insight_type == "shot_surge":
        other_id = next(team_id for team_id in packet.teams if team_id != packet.team_id)
        own, other = facts[f"shots_{packet.team_id}"], facts[f"shots_{other_id}"]
        window = own.window
        if window is None or other.window != window:
            raise ValueError("shot comparison requires one shared window")
        headline = "A burst of recorded shots"
        fan = f"{team} recorded more shots in this spell."
        if selection.fan_frame == "contextual":
            fan += f" The recent count is {own.value} against {other.value} for {packet.teams[other_id]}."
        analyst = f"In minutes {window.start}–{window.end}, {team} recorded {own.value} shots and {packet.teams[other_id]} recorded {other.value}."
        if selection.analyst_frame == "comparison":
            analyst += " This compares shot volume; chance quality and tactical causes are unavailable."
    elif packet.insight_type == "possession_swing":
        previous = facts[f"possession_previous_{packet.team_id}"]
        current = facts[f"possession_current_{packet.team_id}"]
        delta = facts[f"possession_delta_{packet.team_id}"]
        if previous.window is None or current.window is None:
            raise ValueError("possession comparison requires both windows")
        headline = "A rise in measured possession"
        fan = f"{team}'s measured possession share increased."
        if selection.fan_frame == "contextual":
            fan += f" It rose from {previous.value}% to {current.value}%."
        analyst = (f"{team}'s possession rose from {previous.value}% in minutes {previous.window.start}–{previous.window.end} "
                   f"to {current.value}% in minutes {current.window.start}–{current.window.end}.")
        if selection.analyst_frame == "comparison":
            analyst += f" The measured change is {delta.value} percentage points; this does not establish tactical dominance."
    elif packet.insight_type == "recap":
        final = _score(facts["final_score"].value, packet.teams)
        names = list(packet.teams.values())
        headline = "The full-time story"
        fan = f"At full time, {names[0]} {final} {names[1]}."
        analyst = fan
        moments = facts["story_summary"].value
        # Curate compact stories by significance, then render chronologically.
        # Keep score changes ahead of repeated possession windows and cap text
        # even when a synthetic fixture contains many goals.
        entries = []
        goal_actions = {
            "GOAL_OPENS_SCORING": "the opening goal",
            "GOAL_EQUALIZES": "an equalizing goal",
            "GOAL_TAKES_LEAD": "a goal taking the lead",
            "GOAL_EXTENDS_LEAD": "a goal extending the lead",
            "GOAL_REDUCES_DEFICIT": "a goal reducing the deficit",
            "GOAL_RECORDED": "a goal",
        }
        if isinstance(moments, list):
            for index, moment in enumerate(moments):
                if not isinstance(moment, dict):
                    continue
                kind = {"goal": goal_actions.get(moment.get("interpretation_code"), "a goal"),
                        "shot_surge": "a shot surge", "possession_swing": "a measured possession increase"}.get(moment.get("type"))
                if moment.get("type") == "goal" and moment.get("winning_goal") is True:
                    kind = "the winning goal"
                name = packet.teams.get(str(moment.get("team_id")))
                minute = moment.get("minute")
                if kind and name and type(minute) is int and 0 <= minute <= 90:
                    # Winning and equalizing goals receive priority, followed
                    # by other goals, then the strongest supplied pattern.
                    significance = moment.get("significance", 0)
                    significance = significance if type(significance) is int else 0
                    priority = (3000 if moment.get("winning_goal") is True else
                                2000 if moment.get("type") == "goal" else 1000) + significance
                    entries.append((priority, minute, index, moment.get("type"), f"{name}: {kind} at minute {minute}"))
        ranked = sorted(entries, key=lambda item: (-item[0], -item[1], item[2]))
        fan_entries = ranked[:3]
        pattern = next((item for item in ranked if item[3] != "goal"), None)
        if pattern is not None and pattern not in fan_entries:
            fan_entries.append(pattern)
        analyst_entries = ranked[:8]
        def story_text(items):
            return "; ".join(item[4] for item in sorted(items, key=lambda item: (item[1], item[2])))
        if entries:
            if selection.fan_frame == "contextual":
                fan += " Recorded moments include " + story_text(fan_entries) + "."
            analyst += " Selected evidence-backed moments: " + story_text(analyst_entries) + "."
            if len(entries) > len(analyst_entries):
                analyst += " Additional moments remain available in the evidence."
        else:
            fan += " No supported key moments were selected."
            analyst += " Evidence is limited; no supported key moments were selected."
        for prefix, label, suffix in (("shots", "shots", ""), ("passes", "passes", ""), ("possession", "possession", "%")):
            pair = [facts.get(f"{prefix}_{team_id}") for team_id in packet.teams]
            if all(pair):
                first, second = pair
                analyst += f" {label.capitalize()}: {names[0]} {first.value}{suffix}, {names[1]} {second.value}{suffix}."
    else:
        headline = "Limited match evidence"
        fan = "There is not enough supplied evidence to explain a match pattern."
        analyst = "The supplied synthetic record has insufficient supporting facts for a comparative interpretation."
    # Limitations are server-owned and never silently removed by model selection.
    return NarrativeOutput(headline=headline, selected_fact_ids=list(selection.selected_fact_ids),
                           interpretation_code=code, fan_explanation=fan, analyst_explanation=analyst,
                           limitations=list(packet.limitations)).validate_against(packet)


def generate_narrative(packet: ContextPacket, client: Callable[[dict], Any] | None = None, *, allow_live: bool = True) -> dict:
    """Return paired, evidence-rendered narratives and explicit provenance.

    Accepted injected clients set selection_accepted but retain source=template.
    Only an accepted actual Foundry request uses source=foundry. Offline tests and
    preflight configuration never establish live model usefulness or correctness.
    """
    packet = ContextPacket.model_validate(packet)
    if not packet.facts:
        raise ValueError("canonical context must include at least one fact, including limited-evidence contexts")
    start = time.perf_counter()
    source, reason, selection_source, accepted = "template", "not_configured", "deterministic", False
    selection = fallback_selection(packet)
    # Validate the canonical packet can be rendered before contacting a service.
    fallback = render_narrative(packet, selection)
    output = fallback
    try:
        if client is None and not allow_live:
            raise GenerationFailure("offline")
        response = client(_payload(packet)) if client is not None else _call_foundry(_payload(packet))
        candidate = validate_selection(_selection_value(response), packet)
        output = render_narrative(packet, candidate)
        selection, accepted = candidate, True
        if client is None:
            source, reason, selection_source = "foundry", None, "foundry"
        else:
            source, reason, selection_source = "template", "injected_client", "injected"
    except GenerationFailure as exc:
        known = {"not_configured", "invalid_endpoint", "response_too_large", "timeout", "http_error",
                 "transport_error", "malformed_response", "incomplete_response", "model_refusal", "offline"}
        reason = str(exc) if str(exc) in known else "invalid_selection"
    except TimeoutError:
        reason = "timeout"
    except Exception:
        # Do not expose arbitrary service/client exception strings or secrets.
        reason = "invalid_selection"
    metadata = GenerationMetadata(source=source, fallback_reason=reason,
                                  model_version=os.getenv("FOUNDRY_MODEL", "unconfigured") or "unconfigured",
                                  prompt_version=PROMPT_VERSION, latency_ms=float((time.perf_counter() - start) * 1000))
    return NarrativeResult(**{
        **output.model_dump(mode="json"),
        "source": source,
        "selection_source": selection_source,
        "selection_accepted": accepted,
        "selection": selection.model_dump(mode="json"),
        "metadata": metadata.model_dump(mode="json"),
        "validation": {"passed": accepted, "reason": reason, "transport": "injected" if client is not None else "foundry" if allow_live else "offline"},
        "evidence": packet.model_dump(mode="json"),
    }).model_dump(mode="json")
