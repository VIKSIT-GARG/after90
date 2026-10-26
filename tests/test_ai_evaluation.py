"""Evaluation coverage, scenario validity, and offline provenance guarantees."""
import json
from collections import Counter
from pathlib import Path

import pytest

from backend.matchlens.evaluation import (
    CORPUS_PATH, fixture_for_scenario, load_cases, run_case, run_evaluation,
)
from backend.matchlens.fixture import DEFAULT_FIXTURE_PATH, validate_fixture


CASES = load_cases()


def test_corpus_has_sixty_unique_cases_and_all_required_groups():
    assert len(CASES) == 60
    assert len({case["id"] for case in CASES}) == 60
    assert Counter(case["category"] for case in CASES) == {
        "snapshot": 18, "context": 14, "generation": 22, "recap": 6,
    }


def test_all_named_scenarios_validate_and_do_not_modify_golden_fixture():
    before = DEFAULT_FIXTURE_PATH.read_bytes()
    scenarios = {case.get("scenario", "golden") for case in CASES}
    for scenario in scenarios:
        fixture = fixture_for_scenario(scenario)
        validate_fixture(fixture)
        assert fixture.synthetic is True
    assert DEFAULT_FIXTURE_PATH.read_bytes() == before


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_offline_ai_case(case):
    result = run_case(case)
    assert result["status"] == "passed", result["error"]
    assert result["provenance"] in {"deterministic", "injected_client"}


def test_report_does_not_claim_live_accuracy_or_human_usefulness():
    report = run_evaluation([case for case in CASES if case["category"] == "snapshot"])
    assert report["failed"] == 0
    assert report["live_model_metrics"] == {
        "status": "not_measured", "latency_ms": None,
        "token_usage": None, "factual_error_rate": None,
    }
    assert report["human_usefulness"] == {"status": "pending_human_review", "score": None}


def test_corpus_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps({"schema_version": "1.0", "cases": [CASES[0], CASES[0]]}))
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)


def test_scenario_and_unknown_check_fail_explicitly():
    with pytest.raises(ValueError, match="unknown"):
        fixture_for_scenario("not-a-scenario")
    result = run_case({"id": "bad-check", "category": "snapshot", "check": "missing"})
    assert result["status"] == "failed"
