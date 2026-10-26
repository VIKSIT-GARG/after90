"""Public AI integration, recovery and request isolation without cloud calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient

from backend.matchlens import api
from backend.matchlens import narrative
from backend.matchlens.cache import TTLCache
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.provider import ProviderResponse, response_telemetry
from backend.matchlens.service import NarrativeService


@pytest.fixture(autouse=True)
def no_cloud(monkeypatch):
    for key in ('FOUNDRY_RESPONSES_URL', 'FOUNDRY_MODEL', 'FOUNDRY_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(api, 'narrative_service', NarrativeService())


@pytest.fixture
def fixture():
    return load_fixture()


def goal_ids(fixture):
    return [card['id'] for card in snapshot_for_minute(fixture, 90)['insights'] if card['type'] == 'goal']


def offline(packet):
    return generate_narrative(packet, allow_live=False)


def configured(monkeypatch):
    monkeypatch.setenv('FOUNDRY_RESPONSES_URL', 'https://fake.openai.azure.com/openai/v1/responses')
    monkeypatch.setenv('FOUNDRY_MODEL', 'test-deployment')
    monkeypatch.setenv('FOUNDRY_API_KEY', 'not-a-real-secret')


def test_public_insight_has_paired_narrative_overlay_and_legacy_evidence(fixture):
    client = TestClient(api.app)
    response = client.get(f'/api/matches/demo/insights/{goal_ids(fixture)[0]}?as_of_minute=29')
    assert response.status_code == 200
    data = response.json()
    assert data['as_of_minute'] == 29
    assert data['synthetic'] is True
    assert data['source'] == data['metadata']['source'] == 'template'
    assert data['text'] == data['narrative']['fan_explanation']
    assert data['evidence']['event_ids'] == data['narrative']['evidence']['evidence_event_ids']
    assert data['overlay']['match_minute'] == 29
    assert data['overlay']['synthetic'] is True
    assert data['overlay']['source'] == data['source']
    assert data['limitations']
    assert 0 < data['cache_expires_in_seconds'] <= 15
    assert 'not-a-real-secret' not in response.text


def test_future_lookup_rejected_even_after_full_time_cache_fill(fixture):
    client = TestClient(api.app)
    goal_id = goal_ids(fixture)[-1]
    assert client.get(f'/api/matches/demo/insights/{goal_id}?as_of_minute=90').status_code == 200
    assert client.get(f'/api/matches/demo/insights/{goal_id}?as_of_minute=77').status_code == 404
    assert client.get(f'/api/matches/demo/overlay?insight_id={goal_id}&minute=77').status_code == 404


def test_recap_and_story_have_correct_cutoffs():
    client = TestClient(api.app)
    assert client.get('/api/matches/demo/recap?as_of_minute=89').status_code == 409
    response = client.get('/api/matches/demo/recap?as_of_minute=90&mode=analyst').json()
    assert response['final_score'] == {'blue': 2, 'red': 1}
    assert response['text'] == response['narrative']['analyst_explanation']
    assert 'winning goal' in response['text']
    assert response['overlay']['match_minute'] == 90
    early = client.get('/api/matches/demo/story?minute=28').json()
    assert early['as_of_minute'] == 28
    assert all(moment['minute'] <= 28 and not moment['winning_goal'] for moment in early['moments'])
    assert any(moment['type'] == 'shot_surge' for moment in early['moments'])
    empty = client.get('/api/matches/demo/overlay?minute=0').json()
    assert empty == {'as_of_minute': 0, 'overlay': None, 'synthetic': True}


@pytest.mark.parametrize('path', [
    '/api/matches/demo/story?minute=-1', '/api/matches/demo/overlay?minute=91',
    '/api/matches/demo/insights/missing?as_of_minute=oops',
    '/api/matches/demo/recap?mode=unknown',
])
def test_new_query_contracts_reject_invalid_values(path):
    assert TestClient(api.app).get(path).status_code == 422


def test_failure_cache_expires_and_can_recover(fixture, monkeypatch):
    # The provider transport is mocked; this proves recovery logic, not live use.
    configured(monkeypatch)
    now = [100.0]
    calls = []
    def transport(payload):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("synthetic timeout")
        context = payload['context']
        selection = {'selected_fact_ids': [fact['id'] for fact in context['facts']],
                'interpretation_code': context['supported_interpretations'][0],
                'fan_frame': 'contextual', 'analyst_frame': 'comparison',
                'limitations': context['limitations']}
        return ProviderResponse(selection, response_telemetry({}, {}, duration_ms=0))
    monkeypatch.setattr(narrative, '_call_foundry', transport)
    service = NarrativeService(cache=TTLCache(clock=lambda: now[0]), failure_ttl=2)
    first = service.insight(fixture, goal_ids(fixture)[0], 'fan', 29)
    second = service.insight(fixture, goal_ids(fixture)[0], 'analyst', 90)
    assert len(calls) == 1
    assert first['metadata']['fallback_reason'] == 'timeout'
    assert first['evidence'] == second['evidence']
    assert first['text'] != second['text']
    now[0] += 3
    recovered = service.insight(fixture, goal_ids(fixture)[0], 'fan', 90)
    assert len(calls) == 2
    assert recovered['source'] == 'foundry'
    assert recovered['metadata']['fallback_reason'] is None
    assert recovered['cache_expires_in_seconds'] == 600


def test_cache_identity_tracks_fixture_configuration_and_prompt(fixture, monkeypatch):
    calls = []
    def generator(packet):
        calls.append(packet.insight_id)
        return offline(packet)
    service = NarrativeService(generator=generator)
    goal_id = goal_ids(fixture)[0]
    service.insight(fixture, goal_id, 'fan')
    service.insight(fixture, goal_id, 'analyst')
    assert len(calls) == 1
    changed = fixture.model_copy(deep=True)
    changed.players[0].name = 'Changed Fictional Name'
    service.insight(changed, goal_id, 'fan')
    monkeypatch.setenv('FOUNDRY_MODEL', 'another-deployment')
    service.insight(fixture, goal_id, 'fan')
    monkeypatch.setattr(narrative, 'PROMPT_VERSION', 'new-test-prompt')
    service.insight(fixture, goal_id, 'fan')
    assert len(calls) == 4


def test_single_flight_shares_work_and_copies_cached_values():
    cache = TTLCache()
    started, release = Event(), Event()
    calls = []
    def factory():
        calls.append(1)
        started.set()
        assert release.wait(2)
        return {'items': [1]}
    def get():
        return cache.get_or_create('same', factory, ttl=lambda _: 30,
                                   fallback=lambda reason: {'reason': reason})[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(get)
        assert started.wait(2)
        other = [pool.submit(get) for _ in range(3)]
        release.set()
        values = [first.result(2)] + [item.result(2) for item in other]
    assert len(calls) == 1
    values[0]['items'].append(99)
    assert get()['items'] == [1]


def test_different_cache_keys_do_not_hold_a_global_generation_lock():
    cache = TTLCache()
    rendezvous = Barrier(2)
    def get(key):
        def factory():
            rendezvous.wait(timeout=2)
            return {'key': key}
        return cache.get_or_create(key, factory, ttl=lambda _: 30,
                                   fallback=lambda reason: {'reason': reason})[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        one, two = pool.submit(get, 'a'), pool.submit(get, 'b')
        assert one.result(3) == {'key': 'a'}
        assert two.result(3) == {'key': 'b'}


def test_cache_capacity_and_wait_timeout_have_bounded_fallback():
    started, release = Event(), Event()
    cache = TTLCache(max_entries=1, max_inflight=1, wait_timeout=.01)
    def factory():
        started.set()
        assert release.wait(2)
        return {'value': 1}
    def get(key):
        return cache.get_or_create(key, factory, ttl=lambda _: 30,
                                   fallback=lambda reason: {'reason': reason})[0]
    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(get, 'one')
        assert started.wait(2)
        assert get('two') == {'reason': 'concurrency_limit'}
        assert get('one') == {'reason': 'inflight_timeout'}
        release.set()
        assert owner.result(2) == {'value': 1}
    assert len(cache._entries) == 1


def test_model_budget_and_zero_concurrency_fall_back_without_calls(fixture, monkeypatch):
    configured(monkeypatch)
    calls = []
    def generator(packet):
        calls.append(packet.insight_id)
        return offline(packet)
    ids = goal_ids(fixture)
    service = NarrativeService(generator=generator, max_requests=1)
    service.insight(fixture, ids[0], 'fan')
    limited = service.insight(fixture, ids[1], 'fan')
    assert len(calls) == 1
    assert limited['metadata']['fallback_reason'] == 'budget_exhausted'
    disabled = NarrativeService(generator=generator, max_concurrent=0)
    assert disabled.insight(fixture, ids[0], 'fan')['metadata']['fallback_reason'] == 'concurrency_limit'
    assert len(calls) == 1


def test_invalid_or_wrong_moment_generator_output_is_not_cached_as_authoritative(fixture):
    ids = goal_ids(fixture)
    service = NarrativeService(generator=lambda _: {'source': 'foundry', 'text': 'invented'})
    result = service.insight(fixture, ids[0], 'fan')
    assert result['source'] == 'template'
    assert result['metadata']['fallback_reason'] == 'generation_error'
    other = offline(__import__('backend.matchlens.context', fromlist=['build_context']).build_context(fixture, ids[1], 90))
    service = NarrativeService(generator=lambda _: other)
    result = service.insight(fixture, ids[0], 'fan')
    assert result['narrative']['evidence']['insight_id'] == ids[0]
    assert result['metadata']['fallback_reason'] == 'generation_error'


def test_health_does_not_claim_configured_means_verified(monkeypatch):
    configured(monkeypatch)
    health = TestClient(api.app).get('/api/health').json()
    assert health['ai']['configured'] is True
    assert 'not proof' in health['ai']['description']
    assert 'not-a-real-secret' not in str(health)
    assert 'fake.openai.azure.com' not in str(health)
