"""Replay-safe HTTP API for deterministic facts and bounded AI selection."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.models import MatchFixture
from backend.matchlens.service import FullTimeRequired, InsightUnavailable, health_configuration, narrative_service
from backend.matchlens.story import build_story

app = FastAPI(title="After90 synthetic match API", version="0.2.0")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@lru_cache(maxsize=1)
def get_fixture() -> MatchFixture:
    return load_fixture()


@app.get("/api/health")
def health(fixture: MatchFixture = Depends(get_fixture)) -> dict:
    return {"status": "ok", "fixture_version": fixture.fixture_version,
            "synthetic": fixture.synthetic, "ai": health_configuration()}


@app.get("/api/matches/demo")
def demo_snapshot(minute: int = Query(default=0, ge=0, le=90),
                  fixture: MatchFixture = Depends(get_fixture)) -> dict:
    return snapshot_for_minute(fixture, minute)


@app.get("/api/matches/demo/insights/{insight_id}")
def explained_insight(insight_id: str, mode: Literal["fan", "analyst"] = Query(default="fan"),
                      as_of_minute: int = Query(default=90, ge=0, le=90),
                      fixture: MatchFixture = Depends(get_fixture)) -> dict:
    try:
        return narrative_service.insight(fixture, insight_id, mode, as_of_minute)
    except InsightUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/matches/demo/recap")
def match_recap(mode: Literal["fan", "analyst"] = Query(default="fan"),
                as_of_minute: int = Query(default=90, ge=0, le=90),
                fixture: MatchFixture = Depends(get_fixture)) -> dict:
    try:
        return narrative_service.recap(fixture, mode, as_of_minute)
    except FullTimeRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/matches/demo/story")
def match_story(minute: int = Query(default=0, ge=0, le=90),
                fixture: MatchFixture = Depends(get_fixture)) -> dict:
    return build_story(fixture, minute)


@app.get("/api/matches/demo/overlay")
def match_overlay(minute: int = Query(default=0, ge=0, le=90), insight_id: str | None = None,
                  fixture: MatchFixture = Depends(get_fixture)) -> dict:
    try:
        return narrative_service.overlay(fixture, minute, insight_id)
    except InsightUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


if (FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
