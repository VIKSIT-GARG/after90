#!/usr/bin/env python3
"""Check a deployed MatchLens page and deterministic synthetic-match API."""

import argparse
import json
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class SmokeFailure(Exception):
    """A public endpoint did not meet the release contract."""


def fetch(base_url: str, path: str, timeout: float, accept: str) -> tuple[str, str]:
    url = f"{base_url}{path}"
    request = Request(url, headers={"Accept": accept, "User-Agent": "MatchLens-smoke/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise SmokeFailure(f"{path}: response exceeds 2 MB")
            return response.headers.get_content_type(), body.decode("utf-8")
    except HTTPError as exc:
        raise SmokeFailure(f"{path}: HTTP {exc.code}") from exc
    except (URLError, OSError, UnicodeError) as exc:
        raise SmokeFailure(f"{path}: {exc}") from exc


def fetch_json(base_url: str, path: str, timeout: float) -> dict:
    content_type, body = fetch(base_url, path, timeout, "application/json")
    if content_type != "application/json":
        raise SmokeFailure(f"{path}: expected JSON, got {content_type}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SmokeFailure(f"{path}: expected a JSON object")
    return data


def check(base_url: str, timeout: float) -> None:
    health = fetch_json(base_url, "/api/health", timeout)
    if health.get("status") != "ok" or health.get("synthetic") is not True:
        raise SmokeFailure("/api/health: expected status=ok and synthetic=true")
    if not health.get("fixture_version"):
        raise SmokeFailure("/api/health: fixture_version is missing")
    print("PASS /api/health")

    final = None
    for minute in (0, 90):
        path = f"/api/matches/demo?minute={minute}"
        snapshot = fetch_json(base_url, path, timeout)
        if snapshot.get("synthetic") is not True or snapshot.get("minute") != minute:
            raise SmokeFailure(f"{path}: wrong synthetic flag or minute")
        if snapshot.get("fixture_version") != health["fixture_version"]:
            raise SmokeFailure(f"{path}: fixture version differs from health")
        if not isinstance(snapshot.get("score"), dict) or not isinstance(snapshot.get("stats"), dict):
            raise SmokeFailure(f"{path}: score or stats object is missing")
        if minute == 90:
            final = snapshot
        print(f"PASS {path}")

    assert final is not None
    if final["score"] != {"blue": 2, "red": 1}:
        raise SmokeFailure("/api/matches/demo?minute=90: unexpected golden-fixture score")
    goal = next((item for item in final.get("insights", []) if item.get("type") == "goal"), None)
    if not goal:
        raise SmokeFailure("/api/matches/demo?minute=90: goal insight missing")
    for mode in ("fan", "analyst"):
        path = f"/api/matches/demo/insights/{goal['id']}?mode={mode}"
        explanation = fetch_json(base_url, path, timeout)
        if (explanation.get("insight_id") != goal["id"] or
                explanation.get("mode") != mode or
                explanation.get("evidence", {}).get("event_ids") != goal["evidence_event_ids"] or
                not explanation.get("text") or
                explanation.get("source") not in ("foundry", "template")):
            raise SmokeFailure(f"{path}: explanation or evidence mismatch")
        print(f"PASS {path}")

        path = f"/api/matches/demo/recap?mode={mode}"
        recap = fetch_json(base_url, path, timeout)
        if (recap.get("mode") != mode or recap.get("final_score") != final["score"] or
                recap.get("stats") != final["stats"] or not recap.get("text") or
                recap.get("source") not in ("foundry", "template")):
            raise SmokeFailure(f"{path}: recap facts mismatch")
        print(f"PASS {path}")

    content_type, html = fetch(base_url, "/", timeout, "text/html")
    if content_type != "text/html" or "<html" not in html.lower() or 'id="root"' not in html:
        raise SmokeFailure("/: expected the built React HTML page with #root")
    print("PASS / (React HTML)")
    assets = re.findall(r'["\'](/assets/[^"\']+\.js)["\']', html)
    if not assets:
        raise SmokeFailure("/: built JavaScript asset reference is missing")
    asset_type, _ = fetch(base_url, assets[0], timeout, "*/*")
    if asset_type not in ("application/javascript", "text/javascript"):
        raise SmokeFailure(f"{assets[0]}: expected JavaScript, got {asset_type}")
    print(f"PASS {assets[0]} (JavaScript asset)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="public base URL, for example https://example.azurecontainerapps.io")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request (default: 10)")
    args = parser.parse_args()
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username or parts.password:
        parser.error("url must be an HTTP(S) origin without a path, query, fragment, or credentials")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        check(args.url.rstrip("/"), args.timeout)
    except SmokeFailure as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
