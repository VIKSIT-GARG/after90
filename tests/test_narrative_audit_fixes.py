"""Audit regressions: useful frame controls and safe evidence-bound rendering."""
from backend.matchlens.context import build_context
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.evaluation import fixture_for_scenario
from backend.matchlens.fixture import load_fixture, validate_fixture
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.story import build_recap_context


def choose(packet, frame):
    return {
        'selected_fact_ids': [fact.id for fact in packet.facts],
        'interpretation_code': packet.supported_interpretations[0],
        'fan_frame': 'contextual', 'analyst_frame': frame,
        'limitations': [],
    }


def test_recap_analyst_frame_changes_detail_without_changing_evidence():
    packet = build_recap_context(load_fixture())
    evidence = generate_narrative(packet, client=lambda _: choose(packet, 'evidence'))
    comparison = generate_narrative(packet, client=lambda _: choose(packet, 'comparison'))
    assert evidence['selection_accepted'] is comparison['selection_accepted'] is True
    assert evidence['analyst_explanation'] != comparison['analyst_explanation']
    assert 'Differences (' not in evidence['analyst_explanation']
    assert 'shots +4' in comparison['analyst_explanation']
    assert 'possession +6 percentage points' in comparison['analyst_explanation']
    assert evidence['evidence'] == comparison['evidence']
    assert evidence['selected_fact_ids'] == comparison['selected_fact_ids']


def test_empty_recap_explains_unavailable_possession_without_a_false_percentage():
    packet = build_recap_context(fixture_for_scenario('empty'))
    result = generate_narrative(packet, allow_live=False)
    assert 'Measured possession is unavailable' in result['analyst_explanation']
    assert '100%' not in result['analyst_explanation']
    assert not any(fact['id'].startswith('possession_') and fact['id'] != 'possession_available'
                   for fact in result['evidence']['facts'])


def test_long_valid_names_render_bounded_fallback_for_every_insight_and_recap():
    fixture = load_fixture().model_copy(deep=True)
    fixture.teams[0].name = 'Northstar ' + 'Quay ' * 250
    fixture.teams[1].name = 'Copper ' + 'Vale ' * 250
    for player in fixture.players:
        player.name = player.name + ' Name' * 250
    validate_fixture(fixture)
    packets = [build_context(fixture, card['id'], card['minute'])
               for card in snapshot_for_minute(fixture, 90)['insights']]
    packets.append(build_recap_context(fixture))
    for packet in packets:
        result = generate_narrative(packet, allow_live=False)
        assert result['source'] == 'template'
        assert result['metadata']['fallback_reason'] == 'offline'
        assert len(result['fan_explanation']) <= 1200
        assert len(result['analyst_explanation']) <= 2400
        assert result['evidence']['teams'] == packet.teams
        assert '(team 1)' in result['analyst_explanation'] or '(team 2)' in result['analyst_explanation']
    recap = generate_narrative(packets[-1], allow_live=False)
    assert '(team 1)' in recap['analyst_explanation'] and '(team 2)' in recap['analyst_explanation']


def test_truncated_team_labels_remain_distinct_even_when_prefixes_match():
    fixture = load_fixture().model_copy(deep=True)
    fixture.teams[0].name = 'Shared name ' * 100 + 'Alpha'
    fixture.teams[1].name = 'Shared name ' * 100 + 'Beta'
    packet = build_recap_context(fixture)
    result = generate_narrative(packet, allow_live=False)
    assert '(team 1)' in result['fan_explanation']
    assert '(team 2)' in result['fan_explanation']
    assert result['evidence']['teams'] == packet.teams


def test_goal_saturated_analyst_recap_still_mentions_a_supported_pattern():
    packet = build_recap_context(load_fixture())
    raw = packet.model_dump(mode='json')
    story = next(fact for fact in raw['facts'] if fact['id'] == 'story_summary')
    goal = next(moment for moment in story['value'] if moment['type'] == 'goal')
    pattern = next(moment for moment in story['value'] if moment['type'] == 'shot_surge')
    story['value'] = [{**goal, 'id': f'goal-{i}', 'minute': i, 'winning_goal': i == 78}
                      for i in range(1, 79)] + [pattern]
    from backend.matchlens.ai_schemas import ContextPacket
    packet = ContextPacket.model_validate(raw)
    result = generate_narrative(packet, allow_live=False)
    assert 'shot surge' in result['analyst_explanation']
    assert 'Additional moments remain available' in result['analyst_explanation']
    assert len(result['analyst_explanation']) <= 2400


def test_failed_provider_request_retains_attempt_telemetry_and_safe_reason(monkeypatch):
    from backend.matchlens import narrative
    from backend.matchlens.provider import ProviderFailure
    monkeypatch.setenv('FOUNDRY_RESPONSES_URL', 'https://demo.openai.azure.com/openai/v1/responses')
    monkeypatch.setenv('FOUNDRY_API_KEY', 'secret-test-key')
    monkeypatch.setenv('FOUNDRY_MODEL', 'configured-deployment')
    def failed(*args, **kwargs):
        raise ProviderFailure('timeout', attempted=True, telemetry={'provider_request_ms': 3.5})
    monkeypatch.setattr(narrative, 'request_json', failed)
    result = generate_narrative(build_recap_context(load_fixture()))
    assert result['source'] == 'template'
    assert result['metadata']['fallback_reason'] == 'timeout'
    assert result['metadata']['provider_attempted'] is True
    assert result['metadata']['provider']['provider_request_ms'] == 3.5
    assert result['metadata']['provider']['provider_model'] is None


def test_invalid_endpoint_is_preflight_and_injected_selection_is_not_provider_proof(monkeypatch):
    monkeypatch.setenv('FOUNDRY_RESPONSES_URL', 'https://invalid.example/openai/v1/responses')
    monkeypatch.setenv('FOUNDRY_API_KEY', 'secret-test-key')
    monkeypatch.setenv('FOUNDRY_MODEL', 'configured-deployment')
    packet = build_recap_context(load_fixture())
    result = generate_narrative(packet)
    assert result['metadata']['fallback_reason'] == 'invalid_endpoint'
    assert result['metadata']['provider_attempted'] is False
    assert result['metadata']['provider'] is None
    injected = generate_narrative(packet, client=lambda _: choose(packet, 'comparison'))
    assert injected['source'] == 'template'
    assert injected['metadata']['provider_attempted'] is False
    assert injected['metadata']['provider'] is None
