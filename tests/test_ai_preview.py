"""The staged CLI works without credentials and rejects unavailable replay data."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def preview(*args):
    # Even a configured environment must not contact Foundry without --live.
    env = {**os.environ, 'FOUNDRY_API_KEY': 'synthetic-test-key',
           'FOUNDRY_MODEL': 'synthetic-test-model',
           'FOUNDRY_RESPONSES_URL': 'https://unreachable.openai.azure.com/openai/v1/responses'}
    return subprocess.run([sys.executable, 'scripts/preview_ai.py', *args],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)


def test_default_preview_is_offline_and_contextual():
    result = preview('--insight-id', 'goal-e072', '--minute', '29')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['execution_mode'] == 'offline'
    assert payload['context']['as_of_minute'] == 29
    assert payload['narrative']['source'] == 'template'
    assert payload['narrative']['metadata']['fallback_reason'] == 'offline'
    assert 'opened the scoring' in payload['narrative']['fan_explanation']


def test_future_insight_cannot_be_previewed_early():
    result = preview('--insight-id', 'goal-e072', '--minute', '0')
    assert result.returncode == 2
    assert 'unavailable' in json.loads(result.stdout)['error']


def test_full_time_recap_includes_story_and_final_facts():
    result = preview('--recap')
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload['context']['insight_type'] == 'recap'
    assert payload['story']['as_of_minute'] == 90
    assert any(moment['type'] == 'shot_surge' for moment in payload['story']['moments'])
    assert any(fact['id'] == 'final_score' and fact['value'] == {'blue': 2, 'red': 1}
               for fact in payload['context']['facts'])
