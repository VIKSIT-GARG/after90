#!/usr/bin/env python3
"""Plan an Azure OpenAI/Foundry model deployment; only --apply changes Azure.

Uses an already authenticated Azure CLI. Never logs in, retrieves an API key,
registers subscription providers, or writes application secrets.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "azure" / "foundry.json"
REQUIRED = ("AZURE_SUBSCRIPTION_ID", "AFTER90_RESOURCE_GROUP", "AFTER90_LOCATION",
            "AFTER90_FOUNDRY_RESOURCE", "AFTER90_FOUNDRY_DEPLOYMENT",
            "AFTER90_FOUNDRY_MODEL", "AFTER90_FOUNDRY_MODEL_VERSION",
            "AFTER90_FOUNDRY_SKU", "AFTER90_FOUNDRY_CAPACITY")
SKUS = ("Standard", "GlobalStandard", "DataZoneStandard")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    subscription: str
    resource_group: str
    location: str
    resource: str
    deployment: str
    model: str
    model_version: str
    sku: str
    capacity: int
    create_group: bool
    approved: bool

    @property
    def responses_url(self) -> str:
        return f"https://{self.resource}.openai.azure.com/openai/v1/responses"


def _boolean(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name, "false").strip().lower()
    if value not in ("true", "false"):
        raise ConfigurationError(name + " must be true or false")
    return value == "true"


def load_config(env: Mapping[str, str]) -> Config:
    missing = [name for name in REQUIRED if not env.get(name, "").strip()]
    if missing:
        raise ConfigurationError("Missing configuration: " + ", ".join(missing))
    values = {name: env[name].strip() for name in REQUIRED}
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", values["AZURE_SUBSCRIPTION_ID"]):
        raise ConfigurationError("AZURE_SUBSCRIPTION_ID must be a subscription UUID")
    group = values["AFTER90_RESOURCE_GROUP"]
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", group) or group.endswith("."):
        raise ConfigurationError("Invalid AFTER90_RESOURCE_GROUP")
    if not re.fullmatch(r"[a-z][a-z0-9]{1,30}", values["AFTER90_LOCATION"]):
        raise ConfigurationError("AFTER90_LOCATION must be a canonical Azure region")
    resource = values["AFTER90_FOUNDRY_RESOURCE"]
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", resource) or len(resource) < 2 or "--" in resource:
        raise ConfigurationError("AFTER90_FOUNDRY_RESOURCE must be 2-63 lowercase DNS-label characters")
    if len(values["AFTER90_FOUNDRY_DEPLOYMENT"]) > 64:
        raise ConfigurationError("AFTER90_FOUNDRY_DEPLOYMENT must not exceed 64 characters")
    for name in ("AFTER90_FOUNDRY_DEPLOYMENT", "AFTER90_FOUNDRY_MODEL", "AFTER90_FOUNDRY_MODEL_VERSION"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", values[name]):
            raise ConfigurationError(name + " contains unsupported characters or exceeds 128 characters")
    if values["AFTER90_FOUNDRY_SKU"] not in SKUS:
        raise ConfigurationError("AFTER90_FOUNDRY_SKU must be Standard, GlobalStandard or DataZoneStandard")
    raw_capacity = values["AFTER90_FOUNDRY_CAPACITY"]
    if not raw_capacity.isascii() or not raw_capacity.isdecimal() or not 1 <= int(raw_capacity) <= 10:
        raise ConfigurationError("AFTER90_FOUNDRY_CAPACITY must be an integer from 1 to 10")
    return Config(values["AZURE_SUBSCRIPTION_ID"], group, values["AFTER90_LOCATION"], resource,
                  values["AFTER90_FOUNDRY_DEPLOYMENT"], values["AFTER90_FOUNDRY_MODEL"],
                  values["AFTER90_FOUNDRY_MODEL_VERSION"], values["AFTER90_FOUNDRY_SKU"], int(raw_capacity),
                  _boolean(env, "AFTER90_FOUNDRY_CREATE_GROUP"), _boolean(env, "AFTER90_FOUNDRY_APPROVED"))


def arm_parameters(config: Config) -> dict:
    values = {"location": config.location, "resourceName": config.resource,
              "deploymentName": config.deployment, "modelName": config.model,
              "modelVersion": config.model_version, "deploymentSku": config.sku,
              "deploymentCapacity": config.capacity}
    return {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
            "contentVersion": "1.0.0.0", "parameters": {name: {"value": value} for name, value in values.items()}}


def deployment_command(config: Config, parameter_path: str, *, validate: bool = False) -> list[str]:
    return ["az", "deployment", "group", "validate" if validate else "create",
            "--subscription", config.subscription, "--resource-group", config.resource_group,
            "--name", "after90-foundry-setup", "--mode", "Incremental",
            "--template-file", str(TEMPLATE), "--parameters", "@" + parameter_path,
            "--only-show-errors", "--query", "properties.outputs", "--output", "json"]


def public_plan(config: Config) -> dict:
    return {"status": "dry_run", "cloud_mutations": False,
            "azure_cli_installed": shutil.which("az") is not None,
            "resource_group": config.resource_group, "location": config.location,
            "resource": config.resource, "deployment": config.deployment,
            "model": {"name": config.model, "version": config.model_version},
            "deployment_sku": config.sku, "capacity_units": config.capacity,
            "create_resource_group_if_missing": config.create_group,
            "approval_recorded": config.approved, "template": "infra/azure/foundry.json",
            "planned_application_configuration": {"FOUNDRY_RESPONSES_URL": config.responses_url,
                                                   "FOUNDRY_MODEL": config.deployment},
            "operations": (["create_resource_group_if_missing"] if config.create_group else [])
                          + ["validate_arm_deployment", "create_or_update_azure_openai_resource", "create_or_update_model_deployment"],
            "manual_gates": ["subscription_permissions", "resource_name_availability", "registered_cognitive_services_provider",
                             "model_version_region_and_sku_availability", "quota", "approved_spending_ceiling", "structured_output_support",
                             "private_api_key_configuration", "all_type_live_evaluation", "human_usefulness_review"],
            "notes": ["This creates Azure OpenAI in Microsoft Foundry; not a Foundry Agent Service project.",
                      "Capacity is model/SKU quota units, not a dollar or global token spending cap.",
                      "The plan is offline and does not establish availability, quota, cost or successful inference.",
                      "Public data-plane HTTPS is enabled for the existing backend adapter; API-key authentication remains required."]}


def run_azure(command: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess:
    # Never forward raw Azure diagnostics, which can contain private account data.
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)


def apply(config: Config) -> dict:
    if not config.approved:
        return {"status": "blocked", "reason": "cloud_approval_missing", "cloud_mutations": False}
    if shutil.which("az") is None:
        return {"status": "blocked", "reason": "azure_cli_not_installed", "cloud_mutations": False}
    mutated = False
    try:
        result = run_azure(["az", "cloud", "show", "--query", "name", "--output", "tsv"], timeout=20)
        if result.returncode or result.stdout.strip() != "AzureCloud":
            return {"status": "blocked", "reason": "public_azure_cloud_not_verified", "cloud_mutations": False}
        result = run_azure(["az", "account", "show", "--subscription", config.subscription,
                            "--query", "state", "--output", "tsv"], timeout=20)
        if result.returncode or result.stdout.strip() != "Enabled":
            return {"status": "blocked", "reason": "subscription_auth_not_verified", "cloud_mutations": False}
        result = run_azure(["az", "provider", "show", "--subscription", config.subscription,
                            "--namespace", "Microsoft.CognitiveServices", "--query", "registrationState", "--output", "tsv"], timeout=20)
        if result.returncode or result.stdout.strip() != "Registered":
            return {"status": "blocked", "reason": "provider_registration_not_verified", "cloud_mutations": False}
        result = run_azure(["az", "group", "exists", "--subscription", config.subscription,
                            "--name", config.resource_group, "--output", "tsv"], timeout=20)
        if result.returncode or result.stdout.strip().lower() not in ("true", "false"):
            return {"status": "blocked", "reason": "resource_group_check_failed", "cloud_mutations": False}
        if result.stdout.strip().lower() == "false":
            if not config.create_group:
                return {"status": "blocked", "reason": "resource_group_missing", "cloud_mutations": False}
            mutated = True
            result = run_azure(["az", "group", "create", "--subscription", config.subscription,
                                "--name", config.resource_group, "--location", config.location,
                                "--only-show-errors", "--output", "none"])
            if result.returncode:
                return {"status": "failed", "reason": "resource_group_creation_failed", "cloud_mutations": True}
        with tempfile.TemporaryDirectory(prefix="after90-foundry-") as temporary:
            path = Path(temporary) / "parameters.json"
            with path.open("x", encoding="utf-8") as handle:
                os.chmod(path, 0o600)
                json.dump(arm_parameters(config), handle)
            result = run_azure(deployment_command(config, str(path), validate=True))
            if result.returncode:
                return {"status": "failed", "reason": "arm_validation_failed", "cloud_mutations": mutated}
            mutated = True
            result = run_azure(deployment_command(config, str(path)))
        if result.returncode:
            return {"status": "failed", "reason": "arm_deployment_failed", "cloud_mutations": True}
        try:
            outputs = json.loads(result.stdout)
            url = outputs["responsesUrl"]["value"]
            model = outputs["deploymentName"]["value"]
            if url != config.responses_url or model != config.deployment:
                raise ValueError("unexpected output")
        except (ValueError, KeyError, TypeError):
            return {"status": "failed", "reason": "deployment_outputs_not_verified", "cloud_mutations": True}
        return {"status": "deployed", "cloud_mutations": True,
                "application_configuration": {"FOUNDRY_RESPONSES_URL": url, "FOUNDRY_MODEL": model},
                "api_key": "Obtain privately from the resource in Azure/Foundry and configure the backend secret.",
                "live_inference": "not_tested", "next": "Configure FOUNDRY_API_KEY privately, then run all-type live evaluation."}
    except (OSError, subprocess.SubprocessError):
        return {"status": "failed", "reason": "azure_command_failed", "cloud_mutations": mutated}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the reviewed plan through an existing Azure CLI login; may incur Azure charges.")
    args = parser.parse_args()
    try:
        config = load_config(os.environ)
    except ConfigurationError as error:
        print(json.dumps({"status": "invalid_configuration", "reason": str(error), "cloud_mutations": False}))
        return 2
    report = apply(config) if args.apply else public_plan(config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in ("dry_run", "deployed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
