#!/usr/bin/env python3
"""Uncached paired AI evaluation. Offline unless --live is explicitly supplied."""
from __future__ import annotations
import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.matchlens.context import build_context
from backend.matchlens.engine import snapshot_for_minute
from backend.matchlens.fixture import load_fixture
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.story import build_recap_context
from scripts.evaluate_integrated import REQUIRED_AI_TYPES, latency_summary


def evaluation_contexts(fixture=None):
    fixture = fixture if fixture is not None else load_fixture()
    cards = snapshot_for_minute(fixture, 90)['insights']
    return [build_context(fixture, card['id'], card['minute']) for card in cards] + [build_recap_context(fixture)]


def validate_ratings(ratings, review_items):
    """Validate supplied human observations; scores never imply factual safety."""
    known = {item['review_id'] for item in review_items}
    if not isinstance(ratings, list):
        raise ValueError('ratings must be a JSON list')
    seen = set()
    for row in ratings:
        if not isinstance(row, dict) or set(row) != {'review_id', 'A', 'B', 'preferred'}:
            raise ValueError('rating fields must be review_id, A, B, preferred')
        if row['review_id'] not in known or row['review_id'] in seen:
            raise ValueError('unknown or duplicate blind review ID')
        seen.add(row['review_id'])
        if row['preferred'] not in ('A', 'B', 'tie'):
            raise ValueError('preferred must be A, B or tie')
        for side in ('A', 'B'):
            scores = row[side]
            if not isinstance(scores, dict) or set(scores) != {'relevance', 'clarity', 'usefulness'}:
                raise ValueError('each side needs relevance, clarity and usefulness')
            if any(type(value) is not int or not 1 <= value <= 5 for value in scores.values()):
                raise ValueError('human scores must be integers from 1 to 5')
    return {'status': 'provided_not_independently_verified', 'rated_pairs': len(seen),
            'total_pairs': len(known), 'preference_counts': dict(Counter(row['preferred'] for row in ratings)),
            'quality_signoff': 'pending_human_judgment'}


def run_live_evaluation(*, live=False, generator=None, fixture=None):
    provenance = 'injected' if generator is not None else 'live_provider' if live else 'offline'
    contexts = evaluation_contexts(fixture)
    cases, reviews, mappings, durations, service_ms, provider_ms = [], [], [], [], [], []
    coverage = {kind: {'contexts': 0, 'accepted_live': 0} for kind in REQUIRED_AI_TYPES}
    tokens = {key: [] for key in ('input_tokens', 'output_tokens', 'total_tokens')}
    attempted, failed = 0, 0
    for packet in contexts:
        baseline = generate_narrative(packet, allow_live=False)
        start = time.perf_counter()
        try:
            candidate = generator(packet) if generator is not None else generate_narrative(packet, allow_live=live)
            from backend.matchlens.ai_schemas import NarrativeResult
            candidate = NarrativeResult.model_validate(candidate).model_dump(mode='json')
        except Exception as exc:
            failed += 1
            cases.append({'context_id': packet.insight_id, 'type': packet.insight_type, 'status': 'failed', 'error_type': type(exc).__name__})
            continue
        durations.append((time.perf_counter() - start) * 1000)
        metadata = candidate['metadata']
        telemetry = metadata.get('provider') or {}
        real_attempt = provenance == 'live_provider' and metadata.get('provider_attempted') is True
        attempted += int(real_attempt)
        accepted_live = real_attempt and candidate['source'] == 'foundry' and candidate['selection_accepted'] and candidate['selection_source'] == 'foundry'
        coverage[packet.insight_type]['contexts'] += 1
        coverage[packet.insight_type]['accepted_live'] += int(accepted_live)
        service_ms.append(metadata['latency_ms'])
        if real_attempt:
            if telemetry.get('provider_request_ms') is not None:
                provider_ms.append(telemetry['provider_request_ms'])
            for key in tokens:
                if telemetry.get(key) is not None:
                    tokens[key].append(telemetry[key])
        changes = {}
        for mode in ('fan', 'analyst'):
            field = mode + '_explanation'
            changes[mode] = {'text_changed': baseline[field] != candidate[field],
                             'similarity': round(SequenceMatcher(None, baseline[field], candidate[field]).ratio(), 4),
                             'character_delta': len(candidate[field]) - len(baseline[field])}
            digest = hashlib.sha256((':'.join((packet.match_id, packet.fixture_version, packet.insight_id, mode))).encode()).hexdigest()
            candidate_side = 'A' if int(digest[0], 16) % 2 else 'B'
            pair = {candidate_side: candidate[field], 'B' if candidate_side == 'A' else 'A': baseline[field]}
            # Ratings identify the exact rendered pair and evidence, not just the
            # context. A later live run can choose different facts/frames; it must
            # never inherit observations about the earlier output silently.
            review_content = {'mode': mode, 'pair': pair,
                              'canonical_evidence': packet.model_dump(mode='json')}
            review_id = hashlib.sha256(json.dumps(review_content, sort_keys=True,
                                                   separators=(',', ':')).encode()).hexdigest()[:20]
            reviews.append({'review_id': review_id, 'mode': mode, **pair,
                            'canonical_evidence': packet.model_dump(mode='json'),
                            'ratings': {'A': {'relevance': None, 'clarity': None, 'usefulness': None},
                                        'B': {'relevance': None, 'clarity': None, 'usefulness': None}}, 'preferred': None})
            mappings.append({'review_id': review_id, 'candidate_side': candidate_side})
        cases.append({'context_id': packet.insight_id, 'type': packet.insight_type, 'status': 'passed',
                      'source': candidate['source'], 'selection_accepted': candidate['selection_accepted'],
                      'fallback_reason': metadata['fallback_reason'], 'provider_attempted': real_attempt,
                      'provider': telemetry if real_attempt else None, 'model_version': metadata['model_version'],
                      'prompt_version': metadata['prompt_version'],
                      'baseline_selected_fact_ids': baseline['selected_fact_ids'], 'candidate_selected_fact_ids': candidate['selected_fact_ids'],
                      'selection_changed': baseline['selection'] != candidate['selection'], 'wording_changes': changes})
    complete = not failed and all(item['contexts'] > 0 and item['contexts'] == item['accepted_live'] for item in coverage.values())
    return {'schema_version': '1.0', 'synthetic': True, 'provenance': provenance, 'contexts': len(contexts),
            'failed': failed, 'cache': 'bypassed_direct_generation_per_context', 'cases': cases,
            'provider_attempts': attempted, 'type_coverage': coverage,
            'editing_summary': {'selection_changed_contexts': sum(case.get('selection_changed') is True for case in cases),
                                'text_changed_pairs': sum(change['text_changed'] for case in cases for change in case.get('wording_changes', {}).values()),
                                'quality_conclusion': 'not_inferred_from_editing_statistics'},
            'direct_evaluation_latency_ms': latency_summary(durations), 'generation_service_latency_ms': latency_summary(service_ms),
            'provider_request_latency_ms': latency_summary(provider_ms),
            'http_latency_ms': {'status': 'not_applicable_direct_evaluation'},
            'provider_inference_latency_ms': {'status': 'not_measured'},
            'usage': {key: {'observed_attempts': len(values), 'sum': sum(values) if values else None} for key, values in tokens.items()},
            'review_items': reviews, 'blind_mapping_keep_from_reviewers': mappings,
            'acceptance': {'live_foundry': 'demonstrated_all_contexts' if complete else 'not_demonstrated',
                           'human_usefulness': 'pending_human_review'},
            'limitations': ['Text and selection differences measure editing, not superiority or factual safety.',
                           'Provider request timing includes network and provider processing; pure inference is unavailable.',
                           'Missing usage is unknown, never zero; no cost estimate is inferred.',
                           'Injected clients cannot establish live Foundry acceptance.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--require-foundry', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--review-output', type=Path, help='Blinded human-review JSONL; keep full report away from reviewers')
    parser.add_argument('--ratings', type=Path, help='Completed human ratings JSON list')
    args = parser.parse_args()
    if args.require_foundry and not args.live:
        parser.error('--require-foundry requires --live')
    report = run_live_evaluation(live=args.live)
    if args.ratings:
        report['human_ratings'] = validate_ratings(json.loads(args.ratings.read_text()), report['review_items'])
    if args.review_output:
        args.review_output.write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in report['review_items']))
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + '\n')
    print(serialized)
    return int(bool(report['failed']) or (args.require_foundry and report['acceptance']['live_foundry'] != 'demonstrated_all_contexts'))

if __name__ == '__main__':
    raise SystemExit(main())
