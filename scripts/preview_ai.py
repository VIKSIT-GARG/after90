#!/usr/bin/env python3
"""Inspect the Wave 2 pipeline without changing the existing HTTP API.

Default mode is offline and cannot call a model. --live explicitly opts into one
Foundry request; a fallback remains labelled template and is not live proof.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--insight-id', help='Engine insight ID, e.g. goal-e072')
    parser.add_argument('--minute', type=int, default=90, help='Available replay minute, 0-90')
    parser.add_argument('--recap', action='store_true', help='Use the full-time story packet')
    parser.add_argument('--live', action='store_true', help='Allow one configured Foundry request')
    args = parser.parse_args()
    from backend.matchlens.context import build_context
    from backend.matchlens.engine import snapshot_for_minute
    from backend.matchlens.fixture import load_fixture
    from backend.matchlens.narrative import generate_narrative
    from backend.matchlens.story import build_recap_context, build_story

    if args.recap and args.minute != 90:
        parser.error('full-time recap requires --minute 90')
    if args.recap and args.insight_id:
        parser.error('--recap and --insight-id are mutually exclusive')
    try:
        fixture = load_fixture()
        if args.recap:
            packet = build_recap_context(fixture)
        else:
            visible = snapshot_for_minute(fixture, args.minute)['insights']
            insight_id = args.insight_id or next((item['id'] for item in reversed(visible)), None)
            if insight_id is None:
                raise ValueError('no insight is available at this minute; use a later minute or --recap')
            packet = build_context(fixture, insight_id, args.minute)
        result = generate_narrative(packet, allow_live=args.live)
        print(json.dumps({'execution_mode': 'live_requested' if args.live else 'offline',
                          'context': packet.model_dump(mode='json'),
                          'narrative': result,
                          'story': build_story(fixture, args.minute)}, indent=2))
        return 1 if args.live and result['source'] != 'foundry' else 0
    except (ValueError, KeyError) as exc:
        # Errors here describe IDs/configuration, never credential values.
        print(json.dumps({'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
