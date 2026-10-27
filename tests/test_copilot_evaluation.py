import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('evaluate_copilot', Path(__file__).parents[1] / 'scripts/evaluate_copilot.py')
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)


def test_offline_smoke_corpus_passes_without_claiming_live_acceptance():
    report = evaluator.evaluate()
    assert report['passed'] == 7
    assert report['failed'] == 0
    assert report['accepted_live_cases'] == 0
    assert report['live_acceptance'] == 'not_demonstrated'


def test_injected_claim_of_foundry_cannot_close_live_gate():
    def callback(fixture, request, **kwargs):
        result = evaluator.answer_question(fixture, request, allow_live=False)
        if 'peppering' in request.question:
            result['topic'] = 'shots'
        if 'will' not in request.question:
            result['source'] = 'foundry'
            result['metadata'].update(source='foundry', provider_attempted=True, fallback_reason=None)
        return result
    report = evaluator.evaluate(live=True, answerer=callback)
    assert report['passed'] == 7
    assert report['accepted_live_cases'] == 0
    assert report['live_acceptance'] == 'not_demonstrated'


def test_future_evidence_or_context_mismatch_fails_evaluation():
    def callback(fixture, request, **kwargs):
        result = evaluator.answer_question(fixture, request, allow_live=False)
        result['evidence_event_ids'].append(next(event.id for event in fixture.events if event.minute == 90))
        return result
    report = evaluator.evaluate(answerer=callback)
    assert report['failed'] > 0


def test_exceptions_do_not_leak_credentials():
    def callback(*args, **kwargs):
        raise ValueError('private-provider-key')
    report = evaluator.evaluate(answerer=callback)
    assert report['failed'] == 7
    assert 'private-provider-key' not in str(report)
