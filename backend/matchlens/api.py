"""Read-only HTTP API for deterministic synthetic match snapshots."""

from functools import lru_cache

from fastapi import Depends, FastAPI, Query

from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.models import MatchFixture


app = FastAPI(title="MatchLens synthetic match API", version="0.1.0")


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
