"""Coverage and honest measurement gates; no credentials or network required."""
import copy
import json
import pytest
from scripts import evaluate_live_ai as evaluator
from backend.matchlens import narrative


def test_default_never_calls_provider_even_if_configured(monkeypatch):
    for key in ('FOUNDRY_MODEL', 'FOUNDRY_API_KEY', 'FOUNDRY_RESPONSES_URL'):
        monkeypatch.setenv(key, 'configured')
    monkeypatch.setattr(narrative, '_call_foundry', lambda _: pytest.fail('offline evaluator called provider'))
    report = evaluator.run_live_evaluation()
    assert report['failed'] == 0
    assert report['contexts'] == 13
    assert set(report['type_coverage']) == {'goal', 'shot_surge', 'possession_swing', 'recap'}
    assert all(item['contexts'] > 0 for item in report['type_coverage'].values())
    assert report['provider_attempts'] == 0
    assert report['usage']['total_tokens']['sum'] is None
    assert report['acceptance']['live_foundry'] == 'not_demonstrated'
    assert len(report['review_items']) == 26
    assert report['acceptance']['human_usefulness'] == 'pending_human_review'


def accepted(packet):
    return narrative.generate_narrative(packet, client=lambda _: {
        'selected_fact_ids': [fact.id for fact in packet.facts],
        'interpretation_code': packet.supported_interpretations[0],
        'fan_frame': 'contextual', 'analyst_frame': 'comparison', 'limitations': []})


def test_injected_calls_each_context_once_and_never_proves_live():
    seen = []
    def injected(packet):
        seen.append(packet.insight_id)
        result = accepted(packet)
        # Even an injected adapter impersonating accepted transport cannot attest live execution.
        result.update(source='foundry', selection_source='foundry')
        result['metadata'].update(source='foundry', fallback_reason=None, provider_attempted=True)
        result['validation'].update(transport='foundry', reason=None)
        return result
    report = evaluator.run_live_evaluation(live=True, generator=injected)
    assert report['failed'] == 0
    assert len(seen) == len(set(seen)) == 13
    assert report['provider_attempts'] == 0
    assert report['acceptance']['live_foundry'] == 'not_demonstrated'


def test_blind_export_is_stable_and_ratings_are_validated():
    report = evaluator.run_live_evaluation()
    row = report['review_items'][0]
    assert 'candidate_side' not in row and 'source' not in row
    rating = {'review_id': row['review_id'], 'A': {'relevance': 3, 'clarity': 4, 'usefulness': 5},
              'B': {'relevance': 4, 'clarity': 4, 'usefulness': 4}, 'preferred': 'A'}
    assert evaluator.validate_ratings([rating], report['review_items'])['rated_pairs'] == 1
    for invalid in ([rating, rating], [dict(rating, review_id='unknown')]):
        with pytest.raises(ValueError):
            evaluator.validate_ratings(invalid, report['review_items'])
    bad = copy.deepcopy(rating)
    bad['A']['usefulness'] = True
    with pytest.raises(ValueError):
        evaluator.validate_ratings([bad], report['review_items'])
    bad['A']['usefulness'] = 6
    with pytest.raises(ValueError):
        evaluator.validate_ratings([bad], report['review_items'])


def test_cli_requires_explicit_live_and_writes_blind_pairs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr('sys.argv', ['evaluate_live_ai.py', '--require-foundry'])
    with pytest.raises(SystemExit) as exc:
        evaluator.main()
    assert exc.value.code == 2
    output = tmp_path / 'review.jsonl'
    monkeypatch.setattr('sys.argv', ['evaluate_live_ai.py', '--review-output', str(output)])
    assert evaluator.main() == 0
    capsys.readouterr()
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 26 and all('candidate_side' not in row for row in rows)


def test_empty_fixture_evaluation_retains_sparse_evidence_limitations():
    from backend.matchlens.evaluation import fixture_for_scenario
    report = evaluator.run_live_evaluation(fixture=fixture_for_scenario('empty'))
    assert report['failed'] == 0 and report['contexts'] == 1
    evidence = report['review_items'][0]['canonical_evidence']
    assert any('Measured possession is unavailable' in text for text in evidence['limitations'])
    assert not any(fact['id'].startswith('possession_') and fact.get('team_id') for fact in evidence['facts'])
    assert report['acceptance']['live_foundry'] == 'not_demonstrated'


def test_live_gate_requires_every_context_and_all_types(monkeypatch):
    # Simulated transport tests the gate, never constitutes recorded live proof.
    original = evaluator.generate_narrative
    def simulated(packet, *, allow_live=False):
        if not allow_live or packet.insight_type == 'possession_swing':
            return original(packet, allow_live=False)
        result = accepted(packet)
        result.update(source='foundry', selection_source='foundry')
        result['metadata'].update(source='foundry', fallback_reason=None, provider_attempted=True)
        result['validation'].update(transport='foundry', reason=None)
        return result
    monkeypatch.setattr(evaluator, 'generate_narrative', simulated)
    report = evaluator.run_live_evaluation(live=True)
    assert report['provider_attempts'] > 0
    assert report['type_coverage']['possession_swing']['accepted_live'] == 0
    assert report['acceptance']['live_foundry'] == 'not_demonstrated'


def test_high_scoring_fixture_evaluates_patterns_and_recap_without_starvation():
    from backend.matchlens.fixture import load_fixture, validate_fixture
    from backend.matchlens.models import MatchEvent
    fixture = load_fixture().model_copy(deep=True)
    events = []
    for event in fixture.events:
        if event.id in {'e012', 'e054', 'e061', 'e068'}:
            event = event.model_copy(update={'outcome': 'goal'})
            events.append(event)
            events.append(MatchEvent(id='eval-goal-' + event.id, minute=event.minute,
                second=event.second + 1, type='goal', team_id=event.team_id,
                player_id=event.player_id, possession_team_id=event.possession_team_id,
                related_event_id=event.id))
        else:
            events.append(event)
    fixture.events = events
    validate_fixture(fixture)
    report = evaluator.run_live_evaluation(fixture=fixture)
    assert report['failed'] == 0
    assert report['type_coverage']['goal']['contexts'] == 7
    assert all(item['contexts'] > 0 for item in report['type_coverage'].values())
    recap = next(row for row in report['review_items'] if row['canonical_evidence']['insight_type'] == 'recap')
    summary = next(fact['value'] for fact in recap['canonical_evidence']['facts'] if fact['id'] == 'story_summary')
    assert {moment['type'] for moment in summary} == {'goal', 'shot_surge', 'possession_swing'}


def test_ratings_cannot_attach_to_changed_rendered_pairs():
    first = evaluator.run_live_evaluation()
    repeat = evaluator.run_live_evaluation()
    assert [row['review_id'] for row in first['review_items']] == [row['review_id'] for row in repeat['review_items']]

    def changed_output(packet):
        result = narrative.generate_narrative(packet, allow_live=False)
        result['fan_explanation'] += ' Review variant.'
        return result

    changed = evaluator.run_live_evaluation(generator=changed_output)
    assert changed['failed'] == 0
    original_row = first['review_items'][0]
    changed_row = changed['review_items'][0]
    assert original_row['mode'] == changed_row['mode'] == 'fan'
    assert original_row['review_id'] != changed_row['review_id']
    # Unchanged Analyst pairs remain stable regardless of run provenance.
    assert first['review_items'][1]['review_id'] == changed['review_items'][1]['review_id']
    rating = {'review_id': original_row['review_id'],
              'A': {'relevance': 3, 'clarity': 4, 'usefulness': 5},
              'B': {'relevance': 4, 'clarity': 4, 'usefulness': 4}, 'preferred': 'A'}
    assert evaluator.validate_ratings([rating], repeat['review_items'])['rated_pairs'] == 1
    with pytest.raises(ValueError, match='unknown or duplicate'):
        evaluator.validate_ratings([rating], changed['review_items'])
