#!/usr/bin/env python3
"""Check configuration without exposing credentials; optionally probe live Foundry.

Default mode does not call Foundry. --live makes one small generation request to
an allowlisted HTTPS Azure Responses endpoint, with redirects disabled. This is
an access/schema smoke check, not an evaluation of production narrative quality.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("FOUNDRY_RESPONSES_URL", "FOUNDRY_MODEL", "FOUNDRY_API_KEY")
AZURE_ENV = (
    "AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"
)
AZURE_HOST_SUFFIXES = (
    ".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com"
)
MAX_RESPONSE_BYTES = 64 * 1024


class NoRedirect(HTTPRedirectHandler):
    """Never forward a request containing an API key to a redirect target."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def endpoint_valid(value: str) -> bool:
    """Accept only the full public-Azure v1 Responses endpoint shape."""
    try:
        url = urlsplit(value)
        return (
            url.scheme == "https"
            and url.username is None
            and url.password is None
            and url.port in (None, 443)
            and bool(url.hostname)
            and any(url.hostname.endswith(suffix) for suffix in AZURE_HOST_SUFFIXES)
            and url.path == "/openai/v1/responses"
            and not url.query
            and not url.fragment
        )
    except (ValueError, TypeError):
        return False


def azure_auth_status() -> str:
    """Inspect cached CLI auth without returning tenant/account identifiers."""
    cli = shutil.which("az")
    if cli is None:
        return "cli_not_installed"
    try:
        result = subprocess.run(
            [cli, "account", "show", "--query", "state", "--output", "tsv"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "not_verified"
    if result.returncode != 0:
        return "not_authenticated"
    return "cached_account_enabled" if result.stdout.strip() == "Enabled" else "not_verified"


def smoke_input() -> tuple[dict, dict]:
    """Use a real engine-generated goal from the checked-in synthetic fixture."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.matchlens.engine import snapshot_for_minute
    from backend.matchlens.fixture import load_fixture

    fixture = load_fixture()
    goal = next(
        item for item in snapshot_for_minute(fixture, 90)["insights"]
        if item["type"] == "goal"
    )
    packet = {
        "synthetic": True,
        "match_id": fixture.match_id,
        "fixture_version": fixture.fixture_version,
        "insight_id": goal["id"],
        "minute": goal["minute"],
        "team_names": {team.id: team.name for team in fixture.teams},
        "team_id": goal["team_id"],
        "evidence_event_ids": goal["evidence_event_ids"],
        "verified_facts": goal["evidence"],
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "insight_id": {"type": "string", "enum": [goal["id"]]},
            "interpretation_code": {"type": "string", "enum": ["GOAL_RECORDED"]},
            "evidence_event_ids": {
                "type": "array",
                "items": {"type": "string", "enum": goal["evidence_event_ids"]},
            },
            "explanation": {"type": "string"},
        },
        "required": ["insight_id", "interpretation_code", "evidence_event_ids", "explanation"],
    }
    return packet, schema


def response_text(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    pieces = [
        part.get("text")
        for item in response.get("output", [])
        if isinstance(item, dict)
        for part in item.get("content", [])
        if isinstance(part, dict) and part.get("type") == "output_text"
    ]
    return "\n".join(part for part in pieces if isinstance(part, str)) or None


def live_probe(env: Mapping[str, str], timeout: float = 5) -> dict:
    """One request, no retries, no raw exceptions or model text in the report."""
    if not endpoint_valid(env.get("FOUNDRY_RESPONSES_URL", "")):
        return {"status": "fail", "reason": "invalid_endpoint"}
    started = time.monotonic()
    try:
        packet, schema = smoke_input()
        body = {
            "model": env["FOUNDRY_MODEL"],
            "input": [
                {"role": "system", "content": (
                    "Explain the supplied synthetic goal in one concise sentence. "
                    "Use only supplied facts, preserve team attribution, and return the "
                    "requested JSON. Include all supplied evidence event IDs. "
                    "Do not infer tactics, injuries, or future outcomes."
                )},
                {"role": "user", "content": json.dumps(packet, sort_keys=True)},
            ],
            "text": {"format": {
                "type": "json_schema", "name": "after90_access_probe", "strict": True,
                "schema": schema,
            }},
            "max_output_tokens": 400,
            "store": False,
        }
        request = Request(
            env["FOUNDRY_RESPONSES_URL"],
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": env["FOUNDRY_API_KEY"]},
            method="POST",
        )
        with build_opener(NoRedirect()).open(request, timeout=timeout) as handle:
            raw = handle.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return {"status": "fail", "reason": "response_too_large"}
        response = json.loads(raw)
        if not isinstance(response, dict):
            return {"status": "fail", "reason": "invalid_response_or_fixture"}
        if response.get("status") in ("incomplete", "failed", "cancelled"):
            return {"status": "fail", "reason": "incomplete_generation"}
        candidate = json.loads(response_text(response) or "null")
        expected_keys = {"insight_id", "interpretation_code", "evidence_event_ids", "explanation"}
        if not (
            isinstance(candidate, dict)
            and set(candidate) == expected_keys
            and candidate["insight_id"] == packet["insight_id"]
            and candidate["interpretation_code"] == "GOAL_RECORDED"
            and isinstance(candidate["evidence_event_ids"], list)
            and all(isinstance(ref, str) for ref in candidate["evidence_event_ids"])
            and len(candidate["evidence_event_ids"]) == len(packet["evidence_event_ids"])
            and set(candidate["evidence_event_ids"]) == set(packet["evidence_event_ids"])
            and isinstance(candidate["explanation"], str)
            and 1 <= len(candidate["explanation"].strip()) <= 500
        ):
            return {"status": "fail", "reason": "schema_or_evidence_mismatch"}
        return {
            "status": "pass",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "structured_output": "validated",
            "generated_explanation_present": True,
            "semantic_quality": "not_evaluated",
        }
    except HTTPError as error:
        # Never include the exception string, response body, URL, or headers.
        return {"status": "fail", "reason": "http_error", "http_status": error.code}
    except (TimeoutError, URLError, OSError):
        return {"status": "fail", "reason": "network_or_timeout"}
    except (ValueError, TypeError, KeyError, StopIteration, ImportError):
        return {"status": "fail", "reason": "invalid_response_or_fixture"}


def check_readiness(env: Mapping[str, str] | None = None, *, live: bool = False, timeout: float = 5) -> dict:
    env = os.environ if env is None else env
    presence = {name: bool(env.get(name, "").strip()) for name in REQUIRED}
    complete = all(presence.values())
    valid_endpoint = endpoint_valid(env.get("FOUNDRY_RESPONSES_URL", "")) if presence[REQUIRED[0]] else False
    probe = {"status": "live_not_tested", "reason": "live_probe_not_requested"}
    if live:
        probe = live_probe(env, timeout) if complete else {"status": "live_not_tested", "reason": "configuration_missing"}
    state = "not_configured" if not complete else "configured" if valid_endpoint else "invalid_configuration"
    return {
        "configuration": state,
        "environment_presence": presence,
        "endpoint_valid": valid_endpoint,
        "azure_environment_presence": {name: bool(env.get(name, "").strip()) for name in AZURE_ENV},
        "azure_cli_auth": azure_auth_status(),
        "foundry_live_probe": probe,
        "manual_gates": {
            "team_registration": "unverified",
            "subscription_permissions": "unverified",
            "model_quota_and_region": "unverified",
            "spending_limit": "unverified",
            "public_azure_deployment": "unverified",
        },
        "note": "Configuration and cached CLI authentication do not prove quota, deployment permission, registration, or production AI quality.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make one bounded Foundry generation request; may incur model usage charges.")
    parser.add_argument("--timeout", type=float, default=5, help="Live request timeout in seconds (1-15, default 5).")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 15:
        parser.error("--timeout must be between 1 and 15 seconds")
    report = check_readiness(live=args.live, timeout=args.timeout)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["configuration"] != "configured":
        return 2
    if args.live and report["foundry_live_probe"]["status"] != "pass":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
