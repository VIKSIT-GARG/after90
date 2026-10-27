#!/usr/bin/env python3
"""Evaluate replay-safe Match Copilot. Only --live contacts the configured model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.matchlens.copilot import CopilotQuestion, answer_question
from backend.matchlens.fixture import load_fixture

CASES = [
    ('score', "Who's leading?", 29, 'score'),
    ('shots', 'Compare the shots', 29, 'shots'),
    ('passes', 'Compare the passes', 90, 'passes'),
    ('possession', 'Who has more possession?', 90, 'possession'),
    ('moments', 'Show the key moments', 90, 'key_moments'),
    ('paraphrase', 'Which side is peppering the goal?', 29, 'shots'),
    ('future_guard', 'Who will win the match?', 29, 'unsupported'),
]


def evaluate(*, live: bool = False, answerer=None) -> dict:
    fixture = load_fixture()
    run = answer_question if answerer is None else answerer
    cases = []
    live_accepted = 0
    for case_id, question, minute, expected_live in CASES:
        request = CopilotQuestion(question=question, minute=minute, mode='analyst')
        try:
            result = run(fixture, request, allow_live=live)
            metadata = result.get('metadata', {})
            visible = {event.id for event in fixture.events if event.minute <= minute}
            expected = 'unsupported' if case_id == 'paraphrase' and not live else expected_live
            passed = (result.get('synthetic') is True and result.get('question') == question
                      and result.get('as_of_minute') == minute and result.get('topic') == expected
                      and isinstance(result.get('answer'), str) and bool(result['answer'])
                      and set(result.get('evidence_event_ids', [])).issubset(visible))
            if case_id == 'future_guard':
                passed = passed and not metadata.get('provider_attempted') and result.get('source') == 'template'
            real_accepted = (answerer is None and live and passed and case_id != 'future_guard'
                             and result.get('source') == 'foundry' and metadata.get('provider_attempted') is True
                             and metadata.get('fallback_reason') is None)
            live_accepted += int(real_accepted)
            cases.append({'id': case_id, 'as_of_minute': minute, 'expected_topic': expected,
                          'actual_topic': result.get('topic'), 'passed': passed,
                          'source': result.get('source'), 'provider_attempted': metadata.get('provider_attempted', False),
                          'fallback_reason': metadata.get('fallback_reason'), 'accepted_live': real_accepted,
                          'provider': metadata.get('provider'), 'latency_ms': metadata.get('latency_ms')})
        except Exception:
            cases.append({'id': case_id, 'passed': False, 'error': 'evaluation_failed'})
    passed = sum(case['passed'] for case in cases)
    return {'synthetic': True, 'mode': 'injected' if answerer is not None else 'live' if live else 'offline',
            'total': len(cases), 'passed': passed, 'failed': len(cases) - passed,
            'required_live_cases': 6, 'accepted_live_cases': live_accepted,
            'live_acceptance': 'passed' if passed == len(cases) and live_accepted == 6 else 'not_demonstrated',
            'cases': cases,
            'limitations': ['Offline keyword routing does not establish live model paraphrase quality.',
                           'Injected callbacks cannot satisfy live acceptance.',
                           'These fixed questions are a smoke corpus, not a broad language-quality benchmark.',
                           'Request duration includes transport; no pure inference or cost claim is inferred.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='Make up to six real provider requests; consumes model usage.')
    parser.add_argument('--require-foundry', action='store_true')
    args = parser.parse_args()
    if args.require_foundry and not args.live:
        parser.error('--require-foundry requires --live')
    report = evaluate(live=args.live)
    print(json.dumps(report, indent=2))
    return int(bool(report['failed']) or (args.require_foundry and report['live_acceptance'] != 'passed'))


if __name__ == '__main__':
    raise SystemExit(main())
