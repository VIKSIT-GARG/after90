"""Replay-safe API orchestration for bounded AI narrative selection.

Canonical facts are constructed before caching. A paired narrative is generated
once per moment, not once per mode or replay clock tick. Provider configuration,
fixture content and prompt identity are private cache-key inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from threading import BoundedSemaphore, Lock

from . import narrative as narrative_module
from .ai_schemas import ContextPacket, NarrativeResult, Overlay
from .cache import TTLCache
from .context import build_context
from .engine import snapshot_for_minute
from .models import MatchFixture
from .story import build_recap_context, build_story


class InsightUnavailable(ValueError):
    pass


class FullTimeRequired(ValueError):
    pass


def _configured() -> bool:
    return all(os.getenv(name, "").strip() for name in ("FOUNDRY_RESPONSES_URL", "FOUNDRY_API_KEY", "FOUNDRY_MODEL"))


def _identity(fixture: MatchFixture) -> tuple[str, str, str]:
    fixture_hash = hashlib.sha256(fixture.model_dump_json().encode()).hexdigest()
    # Even the endpoint and credential fingerprint remain internal. Key changes
    # invalidate cached failures without including a credential in public output.
    config = json.dumps([os.getenv(name, "").strip() for name in
                         ("FOUNDRY_RESPONSES_URL", "FOUNDRY_MODEL", "FOUNDRY_API_KEY")])
    return fixture_hash, hashlib.sha256(config.encode()).hexdigest(), narrative_module.PROMPT_VERSION


def _limit(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return max(0, min(maximum, value))
    except ValueError:
        return default


def health_configuration() -> dict:
    return {"configured": _configured(), "source_mode": "configured" if _configured() else "template",
            "prompt_version": narrative_module.PROMPT_VERSION,
            "description": "Configuration presence is not proof of live Foundry access."}


def _overlay(packet: ContextPacket, result: dict) -> dict:
    facts = {fact.id: fact for fact in packet.facts}
    teams = list(packet.teams)
    if packet.insight_type == "goal":
        values = facts["score_after"].value
        stat_line = f"{packet.teams[teams[0]]} {values[teams[0]]}–{values[teams[1]]} {packet.teams[teams[1]]} · {packet.minute}'"
    elif packet.insight_type == "shot_surge":
        one, two = (facts[f"shots_{team}"] for team in teams)
        stat_line = (f"Shots: {packet.teams[teams[0]]} {one.value}, {packet.teams[teams[1]]} {two.value} "
                     f"· minutes {one.window.start}–{one.window.end}")
    elif packet.insight_type == "possession_swing":
        before, after = facts[f"possession_previous_{packet.team_id}"], facts[f"possession_current_{packet.team_id}"]
        stat_line = f"{packet.teams[packet.team_id]} possession {before.value}% → {after.value}%"
    else:
        values = facts["final_score"].value
        stat_line = f"Full time: {packet.teams[teams[0]]} {values[teams[0]]}–{values[teams[1]]} {packet.teams[teams[1]]}"
    return Overlay(insight_id=packet.insight_id, match_minute=packet.minute,
                   headline=result["headline"], stat_line=stat_line[:240], display_duration_ms=8000,
                   priority="high" if packet.insight_type in ("goal", "recap") else "medium",
                   evidence_event_ids=list(packet.evidence_event_ids), source=result["source"]).model_dump(mode="json")


class NarrativeService:
    def __init__(self, *, cache: TTLCache | None = None, generator: Callable | None = None,
                 max_requests: int | None = None, max_concurrent: int | None = None,
                 success_ttl: float = 600.0, failure_ttl: float = 15.0):
        self.cache = cache if cache is not None else TTLCache()
        self.generator = generator
        self.max_requests = max_requests if max_requests is not None else _limit("AI_MAX_REQUESTS_PER_PROCESS", 200, 10000)
        concurrency = max_concurrent if max_concurrent is not None else _limit("AI_MAX_CONCURRENT_REQUESTS", 2, 16)
        if self.max_requests < 0 or concurrency < 0:
            raise ValueError("request and concurrency limits must be nonnegative")
        if success_ttl <= 0 or failure_ttl <= 0:
            raise ValueError("cache lifetimes must be positive")
        self._slots = BoundedSemaphore(concurrency)
        self._counter_lock = Lock()
        self._requests_used = 0
        self.success_ttl, self.failure_ttl = success_ttl, failure_ttl

    def _fallback(self, packet: ContextPacket, reason: str) -> dict:
        result = narrative_module.generate_narrative(packet, allow_live=False)
        result["metadata"]["fallback_reason"] = reason
        result["validation"]["reason"] = reason
        return NarrativeResult.model_validate(result).model_dump(mode="json")

    def _generate(self, packet: ContextPacket) -> dict:
        generator = self.generator or narrative_module.generate_narrative
        # No provider configuration means no network request and no spent budget.
        if not _configured():
            return self._validated_generation(generator, packet)
        if not self._slots.acquire(blocking=False):
            return self._fallback(packet, "concurrency_limit")
        try:
            with self._counter_lock:
                if self._requests_used >= self.max_requests:
                    return self._fallback(packet, "budget_exhausted")
                self._requests_used += 1
            return self._validated_generation(generator, packet)
        finally:
            self._slots.release()

    def _validated_generation(self, generator: Callable, packet: ContextPacket) -> dict:
        try:
            result = NarrativeResult.model_validate(generator(packet))
            # A cached response cannot substitute evidence for a different moment.
            if result.evidence != packet:
                return self._fallback(packet, "generation_error")
            return result.model_dump(mode="json")
        except Exception:
            return self._fallback(packet, "generation_error")

    def _result(self, fixture: MatchFixture, packet: ContextPacket) -> tuple[dict, float]:
        key = (*_identity(fixture), packet.insight_id)
        result, remaining = self.cache.get_or_create(
            key, lambda: self._generate(packet),
            ttl=lambda value: self.success_ttl if value["source"] == "foundry" else self.failure_ttl,
            fallback=lambda reason: self._fallback(packet, reason),
        )
        return NarrativeResult.model_validate(result).model_dump(mode="json"), remaining

    @staticmethod
    def _fields(packet: ContextPacket, result: dict, mode: str, as_of_minute: int, remaining: float) -> dict:
        if mode not in ("fan", "analyst"):
            raise ValueError("mode must be fan or analyst")
        return {"mode": mode, "text": result[f"{mode}_explanation"], "source": result["source"],
                "headline": result["headline"], "limitations": result["limitations"],
                "metadata": result["metadata"], "narrative": result,
                "overlay": _overlay(packet, result), "as_of_minute": as_of_minute,
                "cache_expires_in_seconds": remaining, "synthetic": True}

    def insight(self, fixture: MatchFixture, insight_id: str, mode: str, as_of_minute: int = 90) -> dict:
        if mode not in ("fan", "analyst"):
            raise ValueError("mode must be fan or analyst")
        # Validate temporal availability BEFORE touching the cache, including when
        # a future insight was previously requested at full time by another user.
        snapshot = snapshot_for_minute(fixture, as_of_minute)
        card = next((item for item in snapshot["insights"] if item["id"] == insight_id), None)
        if card is None:
            raise InsightUnavailable("insight is unknown or unavailable at this replay minute")
        packet = build_context(fixture, insight_id, card["minute"])
        result, remaining = self._result(fixture, packet)
        evidence = {"type": card["type"], "minute": card["minute"], "team_id": card["team_id"],
                    "event_ids": list(card["evidence_event_ids"]), **card["evidence"]}
        return {**self._fields(packet, result, mode, as_of_minute, remaining),
                "insight_id": insight_id, "evidence": evidence}

    def recap(self, fixture: MatchFixture, mode: str, as_of_minute: int = 90) -> dict:
        if mode not in ("fan", "analyst"):
            raise ValueError("mode must be fan or analyst")
        if as_of_minute != 90:
            raise FullTimeRequired("full-time recap requires as_of_minute=90")
        packet = build_recap_context(fixture)
        result, remaining = self._result(fixture, packet)
        final = snapshot_for_minute(fixture, 90)
        facts = {fact.id: fact.value for fact in packet.facts}
        return {**self._fields(packet, result, mode, 90, remaining),
                "final_score": final["score"], "stats": final["stats"],
                "moment_ids": facts["selected_moment_ids"],
                "evidence": packet.model_dump(mode="json")}

    def overlay(self, fixture: MatchFixture, minute: int, insight_id: str | None = None) -> dict:
        ledger = build_story(fixture, minute)
        if insight_id is None:
            if not ledger["moments"]:
                return {"as_of_minute": minute, "overlay": None, "synthetic": True}
            moment = max(ledger["moments"], key=lambda item: (item["significance"], item["minute"]))
            insight_id = moment["id"]
        response = self.insight(fixture, insight_id, "fan", minute)
        return {"as_of_minute": minute, "overlay": response["overlay"], "synthetic": True}


narrative_service = NarrativeService()
