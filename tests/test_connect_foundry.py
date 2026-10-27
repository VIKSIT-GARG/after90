import importlib.util
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

spec = importlib.util.spec_from_file_location('connect_foundry', Path(__file__).parents[1] / 'scripts/connect_foundry.py')
connector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connector)


@pytest.mark.parametrize('path', ['', '/', '/openai/v1', '/openai/v1/', '/openai/v1/responses'])
def test_resource_endpoint_normalizes_to_responses(path):
    assert connector.responses_endpoint('https://demo.openai.azure.com' + path) == 'https://demo.openai.azure.com/openai/v1/responses'


@pytest.mark.parametrize('value', ['http://demo.openai.azure.com', 'https://evil.test',
    'https://demo.openai.azure.com.evil.test', 'https://key@demo.openai.azure.com',
    'https://demo.openai.azure.com/?api-key=secret', 'https://demo.services.ai.azure.com/api/projects/demo'])
def test_foreign_or_project_endpoint_is_rejected(value):
    with pytest.raises(ValueError):
        connector.responses_endpoint(value)


def test_private_atomic_setup_preserves_other_settings(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# operator settings\nAI_MAX_REQUESTS_PER_PROCESS=8\n')
    connector.configure('https://demo.openai.azure.com/', 'after90-mini', 'private-key-123', path)
    values = dotenv_values(path, interpolate=False)
    assert values['AI_MAX_REQUESTS_PER_PROCESS'] == '8'
    assert values['FOUNDRY_API_KEY'] == 'private-key-123'
    assert '# operator settings' in path.read_text()
    if os.name != 'nt':
        assert path.stat().st_mode & 0o777 == 0o600
    assert connector.status(path, {})['configured'] is True
    assert connector.status(path, {})['live_verified'] is False
    assert 'private-key-123' not in str(connector.status(path, {}))


def test_existing_connection_needs_explicit_replace_and_invalid_change_is_atomic(tmp_path):
    path = tmp_path / '.env'
    connector.configure('https://demo.openai.azure.com', 'model-a', 'old-key-123', path)
    original = path.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        connector.configure('https://demo.openai.azure.com', 'model-b', 'new-key-123', path)
    with pytest.raises(ValueError):
        connector.configure('https://evil.test', 'model-b', 'new-key-123', path, replace=True)
    assert path.read_bytes() == original
    connector.configure('https://demo.openai.azure.com', 'model-b', 'new-key-123', path, replace=True)
    assert dotenv_values(path)['FOUNDRY_MODEL'] == 'model-b'


def test_bad_existing_syntax_and_symlink_are_not_overwritten(tmp_path):
    path = tmp_path / '.env'
    path.write_text("BROKEN='unterminated")
    with pytest.raises(ValueError):
        connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', path)
    assert path.read_text() == "BROKEN='unterminated"
    if os.name != 'nt':
        link = tmp_path / 'link'
        link.symlink_to(path)
        with pytest.raises(ValueError, match='symbolic'):
            connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', link)


def test_process_environment_takes_precedence_without_disclosing_values(tmp_path):
    path = tmp_path / '.env'
    connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', path)
    report = connector.status(path, {'FOUNDRY_API_KEY': ''})
    assert report['configured'] is False
    assert 'private-key-123' not in str(report)


def test_check_never_makes_model_requests(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', path)
    monkeypatch.setattr(connector.sys, 'argv', ['connect_foundry.py', '--env-file', str(path), '--check'])
    for name in connector.NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(connector.subprocess, 'run', lambda *a, **k: pytest.fail('Unexpected model call'))
    assert connector.main() == 0


def test_explicit_verify_runs_both_suites_without_key_in_arguments(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', path)
    monkeypatch.setattr(connector.sys, 'argv', ['connect_foundry.py', '--env-file', str(path), '--check', '--verify'])
    for name in connector.NAMES:
        monkeypatch.delenv(name, raising=False)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['env']['FOUNDRY_API_KEY'] == 'private-key-123'
        assert 'private-key-123' not in str(command)
        return type('Completed', (), {'returncode': 0})()
    monkeypatch.setattr(connector.subprocess, 'run', run)
    assert connector.main() == 0
    assert [Path(command[1]).name for command in calls] == ['evaluate_live_ai.py', 'evaluate_copilot.py']


def test_failed_first_live_suite_stops_further_spend(tmp_path, monkeypatch):
    path = tmp_path / '.env'
    connector.configure('https://demo.openai.azure.com', 'model', 'private-key-123', path)
    monkeypatch.setattr(connector.sys, 'argv', ['connect_foundry.py', '--env-file', str(path), '--check', '--verify'])
    for name in connector.NAMES:
        monkeypatch.delenv(name, raising=False)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return type('Completed', (), {'returncode': 1})()
    monkeypatch.setattr(connector.subprocess, 'run', run)
    assert connector.main() == 1
    assert len(calls) == 1
