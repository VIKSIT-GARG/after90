"""Offline checks of the account-only Foundry bootstrap; never touch Azure."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("after90_setup_foundry", ROOT / "scripts/setup_foundry.py")
setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = setup
SPEC.loader.exec_module(setup)


def environment(**changes):
    return {"AZURE_SUBSCRIPTION_ID": "11111111-2222-3333-4444-555555555555",
            "AFTER90_RESOURCE_GROUP": "after90-demo", "AFTER90_LOCATION": "southindia",
            "AFTER90_FOUNDRY_RESOURCE": "after90-unit-test", "AFTER90_FOUNDRY_DEPLOYMENT": "narrator",
            "AFTER90_FOUNDRY_MODEL": "gpt-4.1-mini", "AFTER90_FOUNDRY_MODEL_VERSION": "2025-04-14",
            "AFTER90_FOUNDRY_SKU": "GlobalStandard", "AFTER90_FOUNDRY_CAPACITY": "1", **changes}


def completed(stdout="", code=0):
    return subprocess.CompletedProcess([], code, stdout, "sensitive diagnostics must remain private")


def outputs(config):
    return json.dumps({"responsesUrl": {"value": config.responses_url}, "deploymentName": {"value": config.deployment}})


def azure_mock(monkeypatch, config, *, group_exists=True, validate_code=0, deploy_output=None):
    calls = []
    captured = []
    def run(command, *, timeout=900):
        calls.append(command)
        if command[1:3] == ["cloud", "show"]: return completed("AzureCloud")
        if command[1:3] == ["account", "show"]: return completed("Enabled")
        if command[1:3] == ["provider", "show"]: return completed("Registered")
        if command[1:3] == ["group", "exists"]: return completed(str(group_exists).lower())
        if command[1:3] == ["group", "create"]: return completed()
        if command[1:3] == ["deployment", "group"]:
            path = Path(command[command.index("--parameters") + 1][1:])
            captured.append((json.loads(path.read_text()), stat.S_IMODE(path.stat().st_mode), path))
            if command[3] == "validate": return completed("{}", validate_code)
            return completed(outputs(config) if deploy_output is None else deploy_output)
        pytest.fail("Unexpected Azure operation")
    monkeypatch.setattr(setup.shutil, "which", lambda _: "/usr/bin/az")
    monkeypatch.setattr(setup, "run_azure", run)
    return calls, captured


def test_plan_is_offline_nonsecret_and_explicit(monkeypatch):
    monkeypatch.setattr(setup, "run_azure", lambda *a, **k: pytest.fail("offline plan contacted Azure"))
    config = setup.load_config(environment(FOUNDRY_API_KEY="private-secret", AZURE_CLIENT_SECRET="another-secret"))
    plan = setup.public_plan(config)
    assert plan["status"] == "dry_run" and plan["cloud_mutations"] is False
    assert plan["planned_application_configuration"]["FOUNDRY_MODEL"] == "narrator"
    assert plan["capacity_units"] == 1
    assert "private-secret" not in json.dumps(plan) and "another-secret" not in json.dumps(plan)
    assert plan["create_resource_group_if_missing"] is False
    params = setup.arm_parameters(config)["parameters"]
    assert params["modelVersion"]["value"] == "2025-04-14"
    assert not any("key" in key.lower() or "secret" in key.lower() for key in params)


@pytest.mark.parametrize("changes", [
    {"AZURE_SUBSCRIPTION_ID": "bad"}, {"AFTER90_RESOURCE_GROUP": "bad;command"},
    {"AFTER90_RESOURCE_GROUP": "trailing."}, {"AFTER90_LOCATION": "South India"},
    {"AFTER90_FOUNDRY_RESOURCE": "UpperCase"}, {"AFTER90_FOUNDRY_RESOURCE": "a"},
    {"AFTER90_FOUNDRY_RESOURCE": "name.openai.azure.com"},
    {"AFTER90_FOUNDRY_RESOURCE": "test--name"}, {"AFTER90_FOUNDRY_RESOURCE": "a" * 64},
    {"AFTER90_FOUNDRY_DEPLOYMENT": "--option"}, {"AFTER90_FOUNDRY_DEPLOYMENT": "a" * 65},
    {"AFTER90_FOUNDRY_MODEL": "gpt;do-something"}, {"AFTER90_FOUNDRY_MODEL_VERSION": ""},
    {"AFTER90_FOUNDRY_MODEL_VERSION": "2025 04 14"}, {"AFTER90_FOUNDRY_SKU": "ProvisionedManaged"},
    {"AFTER90_FOUNDRY_CAPACITY": "0"}, {"AFTER90_FOUNDRY_CAPACITY": "11"},
    {"AFTER90_FOUNDRY_CAPACITY": "1.0"}, {"AFTER90_FOUNDRY_CAPACITY": "١"},
    {"AFTER90_FOUNDRY_APPROVED": "yes"}, {"AFTER90_FOUNDRY_CREATE_GROUP": "yes"},
])
def test_invalid_config_rejected(changes):
    with pytest.raises(setup.ConfigurationError): setup.load_config(environment(**changes))


def test_no_implicit_model_or_version():
    env = environment()
    del env["AFTER90_FOUNDRY_MODEL_VERSION"]
    with pytest.raises(setup.ConfigurationError, match="AFTER90_FOUNDRY_MODEL_VERSION"):
        setup.load_config(env)


def test_apply_requires_deliberate_approval_and_installed_cli(monkeypatch):
    monkeypatch.setattr(setup, "run_azure", lambda *a, **k: pytest.fail("guard contacted Azure"))
    assert setup.apply(setup.load_config(environment()))["reason"] == "cloud_approval_missing"
    monkeypatch.setattr(setup.shutil, "which", lambda _: None)
    assert setup.apply(setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true")))["reason"] == "azure_cli_not_installed"


@pytest.mark.parametrize("stage,response,reason", [
    ("cloud", "AzureUSGovernment", "public_azure_cloud_not_verified"),
    ("account", "Disabled", "subscription_auth_not_verified"),
    ("provider", "NotRegistered", "provider_registration_not_verified"),
])
def test_preflight_blocks_mutation(monkeypatch, stage, response, reason):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true"))
    calls, _ = azure_mock(monkeypatch, config)
    original = setup.run_azure
    def run(command, **kwargs):
        if command[1] == stage: return completed(response)
        return original(command, **kwargs)
    monkeypatch.setattr(setup, "run_azure", run)
    report = setup.apply(config)
    assert report == {"status": "blocked", "reason": reason, "cloud_mutations": False}
    assert not any(command[1:3] == ["deployment", "group"] for command in calls)


def test_missing_group_not_created_without_explicit_flag(monkeypatch):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true"))
    calls, _ = azure_mock(monkeypatch, config, group_exists=False)
    assert setup.apply(config)["reason"] == "resource_group_missing"
    assert not any(command[1:3] == ["group", "create"] for command in calls)


def test_apply_checks_then_validates_then_deploys_and_cleans_parameters(monkeypatch):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true", AFTER90_FOUNDRY_CREATE_GROUP="true"))
    calls, captured = azure_mock(monkeypatch, config, group_exists=False)
    report = setup.apply(config)
    assert report["status"] == "deployed" and report["live_inference"] == "not_tested"
    assert report["application_configuration"] == {"FOUNDRY_RESPONSES_URL": config.responses_url, "FOUNDRY_MODEL": "narrator"}
    operations = [command[1:4] for command in calls]
    assert ["group", "create", "--subscription"] in operations
    assert operations[-2:] == [["deployment", "group", "validate"], ["deployment", "group", "create"]]
    assert all(mode == 0o600 for _, mode, _ in captured) if os.name != "nt" else True
    assert all(not path.exists() for _, _, path in captured)
    assert all("list-keys" not in command and "login" not in command and "set" not in command for command in calls)
    assert "sensitive diagnostics" not in json.dumps(report)


def test_validation_failure_does_not_attempt_model_creation(monkeypatch):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true"))
    calls, _ = azure_mock(monkeypatch, config, validate_code=1)
    assert setup.apply(config) == {"status": "failed", "reason": "arm_validation_failed", "cloud_mutations": False}
    assert not any(command[1:4] == ["deployment", "group", "create"] for command in calls)


def test_partial_group_creation_is_reported_on_validation_failure(monkeypatch):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true", AFTER90_FOUNDRY_CREATE_GROUP="true"))
    azure_mock(monkeypatch, config, group_exists=False, validate_code=1)
    assert setup.apply(config)["cloud_mutations"] is True


@pytest.mark.parametrize("output", ["not json", "[]", '{"responsesUrl":{"value":"https://evil.test"},"deploymentName":{"value":"narrator"}}'])
def test_only_expected_nonsecret_outputs_accepted(monkeypatch, output):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true"))
    azure_mock(monkeypatch, config, deploy_output=output)
    assert setup.apply(config)["reason"] == "deployment_outputs_not_verified"


def test_subprocess_errors_are_sanitized(monkeypatch):
    config = setup.load_config(environment(AFTER90_FOUNDRY_APPROVED="true"))
    monkeypatch.setattr(setup.shutil, "which", lambda _: "/usr/bin/az")
    def fail(*a, **k): raise subprocess.TimeoutExpired("sensitive-command", 20)
    monkeypatch.setattr(setup, "run_azure", fail)
    assert setup.apply(config) == {"status": "failed", "reason": "azure_command_failed", "cloud_mutations": False}


def test_cli_default_is_dry_run_without_azure_or_key(monkeypatch, capsys):
    for name, value in environment(FOUNDRY_API_KEY="test-private-secret").items(): monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["setup_foundry.py"])
    monkeypatch.setattr(setup, "run_azure", lambda *a, **k: pytest.fail("default CLI contacted Azure"))
    assert setup.main() == 0
    report = capsys.readouterr().out
    assert json.loads(report)["status"] == "dry_run" and "test-private-secret" not in report


def test_arm_contract_is_pinned_keyless_output_and_incremental():
    template = json.loads(setup.TEMPLATE.read_text())
    assert all(resource["apiVersion"] == "2025-06-01" for resource in template["resources"])
    account, deployment = template["resources"]
    assert account["kind"] == "OpenAI" and account["properties"]["disableLocalAuth"] is False
    assert deployment["properties"]["versionUpgradeOption"] == "NoAutoUpgrade"
    assert set(template["outputs"]) == {"responsesUrl", "deploymentName"}
    assert "listKeys" not in setup.TEMPLATE.read_text()
    config = setup.load_config(environment())
    command = setup.deployment_command(config, "/tmp/parameters.json")
    assert command[command.index("--mode") + 1] == "Incremental"
    assert "@/tmp/parameters.json" in command
