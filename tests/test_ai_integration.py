"""Integrated HTTP evidence, provenance and recovery checks, with no live model."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient

from backend.matchlens import api, explanations
from backend.matchlens.ai_schemas import NarrativeResult, Overlay
from backend.matchlens.fixture import load_fixture
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.service import NarrativeService

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_integrated.py'
spec = importlib.util.spec_from_file_location('after90_integrated_eval', SCRIPT)
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


@pytest.fixture
def offline_client(monkeypatch):
    # Configuration may exist, but this fixture deliberately never uses transport.
    monkeypatch.setattr(api, 'narrative_service', NarrativeService(
        generator=lambda packet: generate_narrative(packet, allow_live=False)))
    with TestClient(api.app) as client:
        yield client


def test_default_evaluation_never_calls_provider_even_with_configuration(monkeypatch):
    from backend.matchlens import narrative
    monkeypatch.setenv('FOUNDRY_RESPONSES_URL', 'https://test.openai.azure.com/openai/v1/responses')
    monkeypatch.setenv('FOUNDRY_MODEL', 'test-deployment')
    monkeypatch.setenv('FOUNDRY_API_KEY', 'not-a-real-key')
    monkeypatch.setattr(narrative, '_call_foundry', lambda _: pytest.fail('offline evaluation attempted provider'))
    previous = api.narrative_service
    report = evaluator.run_integrated()
    assert api.narrative_service is previous
    assert report['failed'] == 0, report['checks']
    assert report['acceptance']['generation_contract_checks'] == 'passed'
    assert report['acceptance']['live_foundry'] == 'not_demonstrated'
    assert report['acceptance']['human_usefulness'] == 'pending_human_review'
    assert report['acceptance']['browser_accessibility'] == 'not_measured'
    assert report['provider_inference_latency_ms']['status'] == 'not_measured'
    assert report['response_source_counts']['template'] >= 2
    assert report['api_latency_ms']['samples'] > report['generation_service_latency_ms']['samples']
    assert 'not-a-real-key' not in json.dumps(report)


def test_http_route_uses_new_bounded_service_not_legacy_prose(monkeypatch, offline_client):
    monkeypatch.setattr(explanations, 'explain_insight', lambda *_a, **_k: pytest.fail('legacy explanation called'))
    monkeypatch.setattr(explanations, 'build_recap', lambda *_a, **_k: pytest.fail('legacy recap called'))
    response = offline_client.get('/api/matches/demo/insights/goal-e072?mode=fan&as_of_minute=29')
    assert response.status_code == 200
    fan = response.json()
    result = NarrativeResult.model_validate(fan['narrative'])
    assert result.metadata.prompt_version.startswith('after90-bounded-')
    assert result.source == fan['source'] == 'template'
    assert 'opened the scoring' in fan['text']
    assert offline_client.get('/api/matches/demo/recap?as_of_minute=90').status_code == 200


def test_paired_modes_share_generation_and_canonical_evidence(monkeypatch):
    calls = []
    def generator(packet):
        calls.append(packet.insight_id)
        return generate_narrative(packet, allow_live=False)
    monkeypatch.setattr(api, 'narrative_service', NarrativeService(generator=generator))
    with TestClient(api.app) as client:
        fan = client.get('/api/matches/demo/insights/goal-e072?mode=fan&as_of_minute=29').json()
        analyst = client.get('/api/matches/demo/insights/goal-e072?mode=analyst&as_of_minute=78').json()
    assert calls == ['goal-e072']
    assert fan['text'] != analyst['text']
    assert fan['evidence'] == analyst['evidence']
    assert fan['narrative'] == analyst['narrative']
    assert fan['as_of_minute'] == 29 and analyst['as_of_minute'] == 78
    assert analyst['narrative']['evidence']['as_of_minute'] == 29
    assert fan['overlay']['match_minute'] == 29


def test_cached_late_insight_never_leaks_when_seeking_back(offline_client):
    final = offline_client.get('/api/matches/demo?minute=90').json()
    goal = [card for card in final['insights'] if card['type'] == 'goal'][-1]
    assert offline_client.get(f"/api/matches/demo/insights/{goal['id']}?as_of_minute=90").status_code == 200
    assert offline_client.get(f"/api/matches/demo/insights/{goal['id']}?as_of_minute=29").status_code == 404
    assert offline_client.get(f"/api/matches/demo/overlay?minute=29&insight_id={goal['id']}").status_code == 404
    early = offline_client.get('/api/matches/demo/story?minute=29').json()
    assert all(moment['minute'] <= 29 and not moment['winning_goal'] for moment in early['all_moments'])
    assert offline_client.get('/api/matches/demo/recap?as_of_minute=29').status_code == 409


def test_overlay_is_typed_and_empty_before_any_insight(offline_client):
    early = offline_client.get('/api/matches/demo/overlay?minute=0').json()
    assert early == {'as_of_minute': 0, 'overlay': None, 'synthetic': True}
    response = offline_client.get('/api/matches/demo/overlay?minute=29&insight_id=goal-e072').json()
    overlay = Overlay.model_validate(response['overlay'])
    assert overlay.synthetic is True and overlay.insight_id == 'goal-e072'
    fixture = load_fixture()
    assert set(overlay.evidence_event_ids) <= {event.id for event in fixture.events if event.minute <= 29}


def test_invalid_injected_prose_cannot_reach_http_output(monkeypatch):
    def generator(packet):
        return generate_narrative(packet, client=lambda _: {
            'selected_fact_ids': [fact.id for fact in packet.facts],
            'interpretation_code': packet.supported_interpretations[0],
            'fan_frame': 'contextual', 'analyst_frame': 'comparison', 'limitations': [],
            'fan_explanation': 'Northstar Quay did not score.'})
    monkeypatch.setattr(api, 'narrative_service', NarrativeService(generator=generator))
    with TestClient(api.app) as client:
        result = client.get('/api/matches/demo/insights/goal-e072?as_of_minute=29').json()
    assert result['source'] == 'template'
    assert result['metadata']['fallback_reason'] == 'invalid_selection'
    assert result['narrative']['selection_accepted'] is False
    assert 'did not score' not in result['text']


def test_timeout_then_new_service_can_recover_without_false_live_claim(monkeypatch):
    def failed(packet):
        def timeout(_): raise TimeoutError('secret-provider-error')
        return generate_narrative(packet, client=timeout)
    monkeypatch.setattr(api, 'narrative_service', NarrativeService(generator=failed))
    with TestClient(api.app) as client:
        failure = client.get('/api/matches/demo/insights/goal-e072?as_of_minute=29').json()
        assert failure['metadata']['fallback_reason'] == 'timeout'
        assert 'secret-provider-error' not in json.dumps(failure)
        # TTL expiry and concurrent cache behavior are tested by the service tests.
        def accepted(packet):
            return generate_narrative(packet, client=lambda _: {
                'selected_fact_ids': [fact.id for fact in packet.facts],
                'interpretation_code': packet.supported_interpretations[0],
                'fan_frame': 'contextual', 'analyst_frame': 'comparison', 'limitations': []})
        monkeypatch.setattr(api, 'narrative_service', NarrativeService(generator=accepted))
        recovered = client.get('/api/matches/demo/insights/goal-e072?as_of_minute=29').json()
    assert recovered['narrative']['selection_accepted'] is True
    assert recovered['narrative']['selection_source'] == 'injected'
    assert recovered['source'] == 'template'


@pytest.mark.parametrize('url', [
    'https://user:key@example.com', 'https://example.com/path', 'http://example.com',
    'https://example.com?key=secret', 'https://example.com/#fragment',
])
def test_remote_urls_cannot_contain_credentials_or_unsecured_public_origins(url):
    with pytest.raises(ValueError):
        evaluator._base_url(url)


def test_remote_mode_without_live_only_checks_non_generating_routes(monkeypatch):
    requested = []
    with evaluator._local_get(False) as actual_get:
        def remote_get(_base):
            def get(path):
                requested.append(path)
                assert '/insights/' not in path and '/recap' not in path and '/overlay' not in path
                return actual_get(path)
            return get
        monkeypatch.setattr(evaluator, '_remote_get', remote_get)
        report = evaluator.run_integrated(base_url='http://localhost:8000')
    assert report['failed'] == 0
    assert requested and report['generation_requests_enabled'] is False
    assert report['acceptance']['generation_contract_checks'] == 'not_run'
    assert report['response_fallback_rate'] is None
    assert report['api_latency_ms']['samples'] > 0


def test_percentiles_and_invalid_http_report_do_not_claim_success():
    assert evaluator.percentile([], .5) is None
    assert evaluator.latency_summary([10.0])['small_sample'] is True
    assert evaluator.percentile([1., 2., 9.], .95) == 9.
    report = evaluator._evaluate(lambda _path: (503, {'error': 'private body'}), generation=False, provenance='test')
    assert report['failed'] > 0 and report['acceptance']['deterministic_http_checks'] == 'failed'
    assert 'private body' not in json.dumps(report)


def test_require_foundry_needs_explicit_live_opt_in(monkeypatch):
    monkeypatch.setattr('sys.argv', ['evaluate_integrated.py', '--require-foundry'])
    monkeypatch.setattr(evaluator, 'run_integrated', lambda **_: pytest.fail('invalid CLI started evaluation'))
    with pytest.raises(SystemExit) as error:
        evaluator.main()
    assert error.value.code == 2


@pytest.mark.parametrize('sources,expected_exit,expected_requirement', [
    ({'template': 3}, 1, 'failed'),
    ({'template': 2, 'foundry': 1}, 1, 'failed'),
])
def test_require_foundry_fails_when_live_service_only_falls_back(monkeypatch, capsys, sources, expected_exit, expected_requirement):
    monkeypatch.setattr('sys.argv', ['evaluate_integrated.py', '--live', '--require-foundry'])
    monkeypatch.setattr(evaluator, 'run_integrated', lambda **_: {
        'failed': 0, 'response_source_counts': sources,
        'acceptance': {'live_foundry': 'application_reported' if sources.get('foundry') else 'not_demonstrated'},
    })
    assert evaluator.main() == expected_exit
    assert json.loads(capsys.readouterr().out)['acceptance']['foundry_requirement'] == expected_requirement


def test_default_cli_still_passes_offline_without_foundry(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['evaluate_integrated.py'])
    monkeypatch.setattr(evaluator, 'run_integrated', lambda **_: {
        'failed': 0, 'response_source_counts': {'template': 3}, 'acceptance': {},
    })
    assert evaluator.main() == 0
    assert json.loads(capsys.readouterr().out)['acceptance']['foundry_requirement'] == 'not_requested'


def test_require_foundry_passes_only_complete_type_coverage(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['evaluate_integrated.py', '--live', '--require-foundry'])
    monkeypatch.setattr(evaluator, 'run_integrated', lambda **_: {
        'failed': 0, 'acceptance': {},
        'foundry_type_coverage': {kind: {'passed': True} for kind in evaluator.REQUIRED_AI_TYPES}})
    assert evaluator.main() == 0
    assert json.loads(capsys.readouterr().out)['acceptance']['foundry_requirement'] == 'passed'
