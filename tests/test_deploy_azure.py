"""Offline deployment safety and release-contract checks; not an Azure deployment."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('after90_deploy', ROOT / 'scripts/deploy_azure.py')
deploy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deploy
SPEC.loader.exec_module(deploy)


def environment(**updates):
    return {
        'AZURE_SUBSCRIPTION_ID': '11111111-2222-3333-4444-555555555555',
        'AFTER90_RESOURCE_GROUP': 'after90-demo',
        'AFTER90_LOCATION': 'southindia',
        'AFTER90_ENVIRONMENT_NAME': 'after90-env',
        'AFTER90_APP_NAME': 'after90-app',
        'AFTER90_CONTAINER_IMAGE': 'ghcr.io/example/after90:release-123',
        **updates,
    }


def test_default_plan_cannot_call_azure_or_leak_secret(monkeypatch):
    monkeypatch.setattr(deploy, 'run_azure', lambda *a, **k: pytest.fail('dry-run contacted Azure'))
    config = deploy.load_config(environment(FOUNDRY_RESPONSES_URL='https://test.openai.azure.com/openai/v1/responses',
                                          FOUNDRY_MODEL='test-model', FOUNDRY_API_KEY='private-test-secret'))
    plan = deploy.public_plan(config)
    assert plan['status'] == 'dry_run'
    assert plan['cloud_mutations'] is False
    assert plan['foundry_configured'] is True
    assert 'private-test-secret' not in json.dumps(plan)
    assert 'test.openai.azure.com' not in json.dumps(plan)


@pytest.mark.parametrize('changes', [
    {'AZURE_SUBSCRIPTION_ID': 'not-a-uuid'},
    {'AFTER90_APP_NAME': 'UPPERCASE'},
    {'AFTER90_APP_NAME': 'bad--name'},
    {'AFTER90_ENVIRONMENT_NAME': '-starts-with-dash'},
    {'AFTER90_RESOURCE_GROUP': 'injected;command'},
    {'AFTER90_LOCATION': 'south india'},
    {'AFTER90_CONTAINER_IMAGE': 'ghcr.io/example/after90:latest'},
    {'AFTER90_CONTAINER_IMAGE': 'ghcr.io/example/after90'},
    {'AFTER90_CONTAINER_IMAGE': 'ghcr.io/example/after90:tag;command'},
    {'AFTER90_CONTAINER_IMAGE': 'https://ghcr.io/example/after90:v1'},
    {'AFTER90_MIN_REPLICAS': '3'},
    {'AFTER90_MIN_REPLICAS': 'invalid'},
    {'FOUNDRY_API_KEY': 'private-test-secret'},
    {'FOUNDRY_RESPONSES_URL': 'https://example.test/openai/v1/responses', 'FOUNDRY_MODEL': 'm', 'FOUNDRY_API_KEY': 'k'},
    {'FOUNDRY_RESPONSES_URL': 'https://test.openai.azure.com.evil.test/openai/v1/responses', 'FOUNDRY_MODEL': 'm', 'FOUNDRY_API_KEY': 'k'},
    {'FOUNDRY_RESPONSES_URL': 'http://test.openai.azure.com/openai/v1/responses', 'FOUNDRY_MODEL': 'm', 'FOUNDRY_API_KEY': 'k'},
    {'AFTER90_CONTAINER_IMAGE': 'testregistry.azurecr.io/after90:v1'},
    {'AFTER90_REGISTRY_SERVER': 'testregistry.azurecr.io'},
])
def test_invalid_or_ambiguous_configuration_is_rejected(changes):
    with pytest.raises(deploy.ConfigurationError):
        deploy.load_config(environment(**changes))


def test_private_registry_uses_existing_identity_and_versioned_image():
    identity = '/subscriptions/11111111-2222-3333-4444-555555555555/resourceGroups/after90-demo/providers/Microsoft.ManagedIdentity/userAssignedIdentities/after90-pull'
    config = deploy.load_config(environment(AFTER90_CONTAINER_IMAGE='testregistry.azurecr.io/after90:release-123',
                                          AFTER90_REGISTRY_SERVER='testregistry.azurecr.io', AFTER90_REGISTRY_IDENTITY_ID=identity))
    args = deploy.build_command(config)
    assert args[:3] == ['az', 'acr', 'build']
    assert args[args.index('--image') + 1] == 'after90:release-123'
    assert config.registry_identity == identity
    digest = deploy.load_config(environment(AFTER90_CONTAINER_IMAGE='ghcr.io/example/after90@sha256:' + 'a' * 64))
    assert digest.image.endswith('a' * 64)


def test_apply_requires_explicit_cloud_approval(monkeypatch):
    monkeypatch.setattr(deploy, 'run_azure', lambda *a, **k: pytest.fail('unapproved Azure command'))
    assert deploy.apply(deploy.load_config(environment())) == {
        'status': 'blocked', 'reason': 'cloud_approval_missing', 'cloud_mutations': False,
    }


def test_apply_without_cli_is_blocked_before_auth(monkeypatch):
    monkeypatch.setattr(deploy.shutil, 'which', lambda _: None)
    result = deploy.apply(deploy.load_config(environment(AFTER90_CLOUD_APPROVED='true')))
    assert result['reason'] == 'azure_cli_not_installed'
    assert result['cloud_mutations'] is False


def test_failed_auth_or_missing_existing_group_never_deploys(monkeypatch):
    monkeypatch.setattr(deploy.shutil, 'which', lambda _: '/fake/az')
    calls = []
    def invoke(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, '', 'private-test-secret')
    monkeypatch.setattr(deploy, 'run_azure', invoke)
    result = deploy.apply(deploy.load_config(environment(AFTER90_CLOUD_APPROVED='true')))
    assert result['reason'] == 'subscription_auth_not_verified'
    assert len(calls) == 1
    assert 'private-test-secret' not in json.dumps(result)


def test_secure_parameters_are_not_argv_and_are_deleted(monkeypatch):
    monkeypatch.setattr(deploy.shutil, 'which', lambda _: '/fake/az')
    observed = {}
    secret = 'private-test-secret'
    def invoke(args, **kwargs):
        assert secret not in ' '.join(args)
        if args[1:3] == ['account', 'show']:
            return subprocess.CompletedProcess(args, 0, 'Enabled\n', '')
        if args[1:3] == ['group', 'exists']:
            return subprocess.CompletedProcess(args, 0, 'true\n', '')
        path = Path(args[args.index('--parameters') + 1].removeprefix('@'))
        observed['path'] = path
        if os.name != "nt":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert json.loads(path.read_text())['parameters']['foundryApiKey']['value'] == secret
        return subprocess.CompletedProcess(args, 0, 'https://after90-app.test.southindia.azurecontainerapps.io\n', '')
    monkeypatch.setattr(deploy, 'run_azure', invoke)
    config = deploy.load_config(environment(AFTER90_CLOUD_APPROVED='true',
                                          FOUNDRY_RESPONSES_URL='https://test.openai.azure.com/openai/v1/responses',
                                          FOUNDRY_MODEL='test-model', FOUNDRY_API_KEY=secret))
    result = deploy.apply(config)
    assert result['status'] == 'deployed_unverified'
    assert not observed['path'].exists()
    assert secret not in json.dumps(result)


def test_provider_errors_are_sanitized_and_parameter_cleanup_survives_failure(monkeypatch):
    monkeypatch.setattr(deploy.shutil, 'which', lambda _: '/fake/az')
    observed = {}
    def invoke(args, **kwargs):
        if args[1:3] == ['account', 'show']:
            return subprocess.CompletedProcess(args, 0, 'Enabled\n', '')
        if args[1:3] == ['group', 'exists']:
            return subprocess.CompletedProcess(args, 0, 'true\n', '')
        observed['path'] = Path(args[args.index('--parameters') + 1].removeprefix('@'))
        raise subprocess.TimeoutExpired(args, 1, output='private-test-secret')
    monkeypatch.setattr(deploy, 'run_azure', invoke)
    result = deploy.apply(deploy.load_config(environment(AFTER90_CLOUD_APPROVED='true')))
    assert result['reason'] == 'azure_command_timeout_state_unknown'
    assert not observed['path'].exists()
    assert 'private-test-secret' not in json.dumps(result)


def test_arm_template_has_bounded_scale_health_probes_and_server_only_secret():
    template = json.loads(deploy.TEMPLATE.read_text())
    assert template['parameters']['foundryApiKey']['type'] == 'secureString'
    resources = {resource['type']: resource for resource in template['resources']}
    assert set(resources) == {'Microsoft.App/managedEnvironments', 'Microsoft.App/containerApps'}
    app = resources['Microsoft.App/containerApps']
    assert app['apiVersion'] == '2025-01-01'
    assert app['properties']['configuration']['ingress']['targetPort'] == 8000
    assert app['properties']['configuration']['ingress']['allowInsecure'] is False
    container = app['properties']['template']['containers'][0]
    assert container['resources'] == {'cpu': 0.5, 'memory': '1Gi'}
    assert {probe['type'] for probe in container['probes']} == {'Startup', 'Readiness', 'Liveness'}
    assert all(probe['httpGet']['path'] == '/api/health' for probe in container['probes'])
    assert template['parameters']['maxReplicas']['maxValue'] == 2
    assert 'secretRef' in container['env']


def test_cli_default_reports_configuration_block_without_mutation():
    env = {key: value for key, value in os.environ.items() if key not in deploy.REQUIRED + deploy.FOUNDRY}
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/deploy_azure.py')], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload['status'] == 'blocked' and payload['cloud_mutations'] is False
