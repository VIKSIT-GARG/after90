#!/usr/bin/env python3
"""Evaluate the HTTP pipeline, offline by default, with explicit provenance.

--url performs bounded read-only deployed-service checks. Remote generation needs
--live because an API request could cause the remote server to call Foundry.
No API keys are sent to a supplied application URL.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAX_BYTES = 2 * 1024 * 1024


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile; a single observation is not a distribution."""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(fraction * len(ordered)) - 1)], 3)


def latency_summary(values: list[float]) -> dict:
    return {"samples": len(values), "p50": percentile(values, .5), "p95": percentile(values, .95),
            "unit": "ms", "small_sample": len(values) < 20}


def _base_url(value: str) -> str:
    url = urlsplit(value)
    localhost = url.hostname in {"localhost", "127.0.0.1", "::1"}
    if (url.scheme not in ({"http", "https"} if localhost else {"https"}) or not url.hostname
            or url.username is not None or url.password is not None or url.query or url.fragment
            or url.path not in ("", "/")):
        raise ValueError("application URL must be HTTPS (HTTP allowed only on localhost), without credentials, path or query")
    return value.rstrip("/")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _remote_get(base: str) -> Callable[[str], tuple[int, dict]]:
    opener = build_opener(_NoRedirect())
    def get(path: str) -> tuple[int, dict]:
        request = Request(base + path, headers={"Accept": "application/json"})
        try:
            with opener.open(request, timeout=12) as response:
                code, raw = response.status, response.read(MAX_BYTES + 1)
        except HTTPError as exc:
            code, raw = exc.code, exc.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("application response exceeded evaluation size limit")
        return code, json.loads(raw)
    return get


@contextmanager
def _local_get(live: bool):
    from fastapi.testclient import TestClient
    from backend.matchlens import api
    from backend.matchlens.narrative import generate_narrative
    from backend.matchlens.service import NarrativeService
    previous_service = api.narrative_service
    generator = (lambda packet: generate_narrative(packet, allow_live=live))
    api.narrative_service = NarrativeService(generator=generator)
    try:
        with TestClient(api.app) as client:
            def get(path: str) -> tuple[int, dict]:
                response = client.get(path)
                return response.status_code, response.json()
            yield get
    finally:
        api.narrative_service = previous_service


def _evaluate(get: Callable, *, generation: bool, provenance: str) -> dict:
    checks, observations, latencies = [], [], []
    def fetch(path: str, expected: int = 200) -> dict:
        started = time.perf_counter()
        status, payload = get(path)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        assert status == expected, f"expected HTTP {expected}, received {status}"
        observations.append({"path": path, "status": status, "api_latency_ms": round(elapsed, 3), "payload": payload})
        return payload
    def check(name: str, action: Callable):
        try:
            action()
            checks.append({"id": name, "status": "passed"})
        except Exception as exc:
            # Never print transport bodies or arbitrary endpoint/provider errors.
            checks.append({"id": name, "status": "failed", "error_type": type(exc).__name__})

    state = {}
    def health():
        payload = fetch("/api/health")
        assert payload["status"] == "ok" and payload["synthetic"] is True
    check("synthetic-health", health)
    def snapshots():
        before = fetch("/api/matches/demo?minute=0")
        final = fetch("/api/matches/demo?minute=90")
        assert before["synthetic"] is True and final["synthetic"] is True
        assert not before["insights"]
        assert sum(final["stats"]["possession_percent"].values()) == 100
        state["final"] = final
        state["goal"] = next(i for i in final["insights"] if i["type"] == "goal")
    check("replay-snapshots", snapshots)
    def story():
        early = fetch("/api/matches/demo/story?minute=0")
        final = fetch("/api/matches/demo/story?minute=90")
        assert early["synthetic"] is True and not early["moments"]
        assert final["as_of_minute"] == 90 and final["moments"]
    check("story-cutoff", story)
    if generation:
        def modes():
            goal = state["goal"]
            fan = fetch(f"/api/matches/demo/insights/{goal['id']}?mode=fan&as_of_minute={goal['minute']}")
            analyst = fetch(f"/api/matches/demo/insights/{goal['id']}?mode=analyst&as_of_minute={goal['minute']}")
            from backend.matchlens.ai_schemas import NarrativeResult, Overlay
            for response in (fan, analyst):
                NarrativeResult.model_validate(response["narrative"])
                Overlay.model_validate(response["overlay"])
                assert response["source"] == response["narrative"]["source"] == response["metadata"]["source"]
                assert response["synthetic"] is True
            assert fan["text"] != analyst["text"]
            assert fan["evidence"] == analyst["evidence"]
            assert fan["narrative"]["selected_fact_ids"] == analyst["narrative"]["selected_fact_ids"]
            assert fan["narrative"]["evidence"]["as_of_minute"] <= goal["minute"]
            state["fan"] = fan
        check("paired-mode-facts", modes)
        def no_legacy_path():
            fan = state["fan"]
            assert fan["narrative"]["metadata"]["prompt_version"].startswith("after90-bounded-")
            assert fan["headline"] == fan["narrative"]["headline"]
            assert fan["limitations"] == fan["narrative"]["evidence"]["limitations"]
        check("bounded-service-contract", no_legacy_path)
        def future():
            goal = state["goal"]
            code, _ = get(f"/api/matches/demo/insights/{goal['id']}?as_of_minute=0")
            assert code in (404, 409)
        check("future-insight-unavailable", future)
        def recap():
            payload = fetch("/api/matches/demo/recap?mode=analyst&as_of_minute=90")
            assert payload["final_score"] == state["final"]["score"]
            assert payload["stats"] == state["final"]["stats"]
            code, _ = get("/api/matches/demo/recap?as_of_minute=20")
            assert code == 409
        check("recap-canonical-facts", recap)
        def overlay():
            goal = state["goal"]
            payload = fetch(f"/api/matches/demo/overlay?minute={goal['minute']}&insight_id={goal['id']}")
            item = payload["overlay"]
            assert payload["synthetic"] is True and item["synthetic"] is True
            assert item["insight_id"] == goal["id"] and item["match_minute"] <= goal["minute"]
            assert set(goal["evidence_event_ids"]) <= set(item["evidence_event_ids"])
        check("overlay-evidence-and-time", overlay)
    sources, reasons = Counter(), Counter()
    service_latencies = []
    baselines = []
    for obs in observations:
        payload = obs["payload"]
        narrative = payload.get("narrative")
        if not isinstance(narrative, dict):
            continue
        source = narrative.get("source", "unknown")
        sources[source] += 1
        metadata = narrative.get("metadata", {})
        reason = metadata.get("fallback_reason")
        if reason:
            reasons[reason] += 1
        if type(metadata.get("latency_ms")) in (int, float):
            service_latencies.append(metadata["latency_ms"])
        baselines.append({"path": obs["path"], "source": source,
                          "selected_fact_count": len(narrative.get("selected_fact_ids", [])),
                          "paired_wording_differs": narrative.get("fan_explanation") != narrative.get("analyst_explanation")})
    count = sum(sources.values())
    return {
        "schema_version": "1.0", "synthetic": True, "transport": provenance,
        "generation_requests_enabled": generation,
        "passed": sum(c["status"] == "passed" for c in checks),
        "failed": sum(c["status"] == "failed" for c in checks), "checks": checks,
        "api_latency_ms": latency_summary(latencies),
        "generation_service_latency_ms": latency_summary(service_latencies),
        "provider_inference_latency_ms": {"status": "not_measured", "p50": None, "p95": None},
        "response_source_counts": dict(sources), "response_fallback_reasons": dict(reasons),
        "response_fallback_rate": round(sources["template"] / count, 4) if count else None,
        "metric_limitations": ["Response counts can include cached paired-mode responses; they are not independent model attempts.",
                               "API latency includes HTTP/application work. Generation-service latency includes adapter, validation and rendering, not pure model inference.",
                               "Remote provenance is reported by the application and is not independently attested."],
        "template_baseline": {"status": "structural_comparison_only", "observations": baselines,
                              "human_preference_or_ai_improvement": "not_measured"},
        "acceptance": {"generation_contract_checks": "passed" if generation and all(c["status"] == "passed" for c in checks) else "failed" if generation else "not_run",
                       "deterministic_http_checks": "passed" if all(c["status"] == "passed" for c in checks) else "failed",
                       "live_foundry": "application_reported" if sources["foundry"] else "not_demonstrated",
                       "human_usefulness": "pending_human_review", "browser_accessibility": "not_measured",
                       "public_azure_deployment": "not_attested"},
    }


def run_integrated(*, base_url: str | None = None, live: bool = False) -> dict:
    if base_url:
        return _evaluate(_remote_get(_base_url(base_url)), generation=live, provenance="remote_application")
    with _local_get(live) as get:
        return _evaluate(get, generation=True, provenance="local_testclient_live_enabled" if live else "local_testclient_offline")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Application base URL, never a model endpoint or credential-bearing URL")
    parser.add_argument("--live", action="store_true", help="Explicitly allow generation that may contact configured Foundry")
    parser.add_argument("--require-foundry", action="store_true", help="Fail unless a response reports accepted Foundry selection; requires --live")
    args = parser.parse_args()
    if args.require_foundry and not args.live:
        parser.error("--require-foundry requires --live")
    try:
        report = run_integrated(base_url=args.url, live=args.live)
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__, "details": "Evaluation could not start; inspect local configuration without exposing secrets."}))
        return 2
    foundry_observed = report.get("response_source_counts", {}).get("foundry", 0) > 0
    report["acceptance"]["foundry_requirement"] = (
        "passed" if foundry_observed else "failed"
    ) if args.require_foundry else "not_requested"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failed"] or (args.require_foundry and not foundry_observed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
