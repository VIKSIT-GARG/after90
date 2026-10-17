"""Read-only HTTP API for deterministic synthetic match snapshots."""

from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.explanations import build_recap, explain_insight
from backend.matchlens.fixture import load_fixture
from backend.matchlens.models import MatchFixture


app = FastAPI(title="MatchLens synthetic match API", version="0.1.0")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_explanation_cache: dict[tuple[str, str, str, str], dict] = {}
_recap_cache: dict[tuple[str, str, str], dict] = {}
_cache_lock = Lock()


@lru_cache(maxsize=1)
def get_fixture() -> MatchFixture:
    """Load the versioned demo fixture once for the lifetime of the API process."""

    return load_fixture()


@app.get("/api/health")
def health(fixture: MatchFixture = Depends(get_fixture)) -> dict:
    return {
        "status": "ok",
        "fixture_version": fixture.fixture_version,
        "synthetic": fixture.synthetic,
    }


@app.get("/api/matches/demo")
def demo_snapshot(
    minute: int = Query(default=0, ge=0, le=90),
    fixture: MatchFixture = Depends(get_fixture),
) -> dict:
    """Return a snapshot derived only from events at or before ``minute``."""

    return snapshot_for_minute(fixture, minute)


@app.get("/api/matches/demo/insights/{insight_id}")
def explained_insight(
    insight_id: str,
    mode: Literal["fan", "analyst"] = Query(default="fan"),
    fixture: MatchFixture = Depends(get_fixture),
) -> dict:
    """Explain one computed insight without allowing the wording to edit its evidence."""

    insight = next(
        (
            item
            for item in snapshot_for_minute(fixture, 90)["insights"]
            if item["id"] == insight_id
        ),
        None,
    )
    if insight is None:
        raise HTTPException(status_code=404, detail="insight not found")
    key = (fixture.match_id, fixture.fixture_version, insight_id, mode)
    with _cache_lock:
        if key not in _explanation_cache:
            _explanation_cache[key] = explain_insight(fixture, insight, mode)
        return _explanation_cache[key]


@app.get("/api/matches/demo/recap")
def match_recap(
    mode: Literal["fan", "analyst"] = Query(default="fan"),
    fixture: MatchFixture = Depends(get_fixture),
) -> dict:
    """Summarize verified full-time facts for the selected viewer mode."""

    key = (fixture.match_id, fixture.fixture_version, mode)
    with _cache_lock:
        if key not in _recap_cache:
            _recap_cache[key] = build_recap(fixture, mode)
        return _recap_cache[key]


if (FRONTEND_DIST / "index.html").is_file():
    # Keep API routes above this catch-all mount. Docker copies the Vite build here.
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
