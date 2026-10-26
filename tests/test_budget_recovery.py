"""Fixed-window provider quotas recover deterministically without cloud calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from backend.matchlens import api
from backend.matchlens.cache import TTLCache
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.service import NarrativeService


@pytest.fixture(autouse=True)
def provider_config(monkeypatch):
    for key in ('FOUNDRY_RESPONSES_URL', 'FOUNDRY_MODEL', 'FOUNDRY_API_KEY'):
        monkeypatch.setenv(key, 'private-test-value')


def setup_service(**kwargs):
    now = [100.0]
    calls = []
    def generator(packet):
        calls.append(packet.insight_id)
        return generate_narrative(packet, allow_live=False)
    service = NarrativeService(cache=TTLCache(clock=lambda: now[0]), generator=generator,
                               clock=lambda: now[0], budget_window_seconds=10, **kwargs)
    fixture = load_fixture()
    goals = [card['id'] for card in snapshot_for_minute(fixture, 90)['insights'] if card['type'] == 'goal']
    return service, fixture, goals, now, calls


def test_exhausted_result_recovers_at_exact_boundary_without_restart():
    service, fixture, goals, now, calls = setup_service(max_requests=1)
    service.insight(fixture, goals[0], 'fan', 90)
    now[0] = 109.999
    rejected = service.insight(fixture, goals[1], 'fan', 90)
    assert rejected['metadata']['fallback_reason'] == 'budget_exhausted'
    assert rejected['cache_expires_in_seconds'] == 0
    assert service.budget_status()['remaining'] == 0
    now[0] = 110.0
    recovered = service.insight(fixture, goals[1], 'analyst', 90)
    assert recovered['metadata']['fallback_reason'] != 'budget_exhausted'
    assert len(calls) == 2
    assert service.budget_status()['used'] == 1


def test_idle_windows_do_not_accumulate_credits_and_health_is_read_only(monkeypatch):
    service, fixture, goals, now, calls = setup_service(max_requests=2)
    service.insight(fixture, goals[0], 'fan', 90)
    now[0] = 135.0
    monkeypatch.setattr(api, 'narrative_service', service)
    response = TestClient(api.app).get('/api/health')
    budget = response.json()['ai']['budget']
    assert budget == {'scope': 'per_process', 'policy': 'fixed_window', 'limit': 2,
                      'used': 0, 'remaining': 2, 'exhausted': False,
                      'window_seconds': 10.0, 'reset_after_seconds': 5.0}
    assert 'private-test-value' not in response.text
    assert len(calls) == 1


def test_zero_budget_never_attempts_provider_even_after_reset():
    service, fixture, goals, now, calls = setup_service(max_requests=0)
    for minute in (100.0, 110.0, 1000.0):
        now[0] = minute
        assert service.insight(fixture, goals[0], 'fan', 90)['metadata']['fallback_reason'] == 'budget_exhausted'
    assert not calls
    assert service.budget_status()['exhausted'] is True


def test_concurrent_distinct_requests_cannot_overspend():
    service, fixture, goals, now, calls = setup_service(max_requests=1, max_concurrent=16)
    # Bypass cache identity deliberately to exercise quota arbitration directly.
    from backend.matchlens.context import build_context
    packet = build_context(fixture, goals[0], 90)
    gate = Barrier(12)
    def request(_):
        gate.wait(timeout=3)
        return service._generate(packet)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(request, range(12)))
    assert len(calls) == 1
    assert sum(result['metadata']['fallback_reason'] == 'budget_exhausted' for result in results) == 11
    assert service.budget_status()['used'] == 1


def test_unconfigured_generation_does_not_spend_budget(monkeypatch):
    service, fixture, goals, now, calls = setup_service(max_requests=0)
    monkeypatch.delenv('FOUNDRY_API_KEY')
    result = service.insight(fixture, goals[0], 'fan', 90)
    assert result['metadata']['fallback_reason'] == 'offline'
    assert len(calls) == 1
    assert service.budget_status()['used'] == 0


@pytest.mark.parametrize('window', [0, -1, float('nan'), float('inf'), True])
def test_explicit_invalid_windows_rejected(window):
    with pytest.raises(ValueError):
        NarrativeService(budget_window_seconds=window)


@pytest.mark.parametrize('window', ['0', '-1', 'nan', 'inf', 'bad', '999999'])
def test_invalid_environment_windows_use_safe_default(monkeypatch, window):
    monkeypatch.setenv('AI_BUDGET_WINDOW_SECONDS', window)
    assert NarrativeService().budget_status()['window_seconds'] == 3600
