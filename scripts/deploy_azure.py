#!/usr/bin/env python3
"""Prepare an offline Azure deployment plan; cloud mutation requires --apply.

No login, registry, role assignment, resource group, or paid model is created.
Deploys the supplied versioned image into an existing approved resource group.
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
from typing import Any, Mapping
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "infra" / "azure" / "main.json"
REQUIRED = (
    "AZURE_SUBSCRIPTION_ID", "AFTER90_RESOURCE_GROUP", "AFTER90_LOCATION",
    "AFTER90_ENVIRONMENT_NAME", "AFTER90_APP_NAME", "AFTER90_CONTAINER_IMAGE",
)
FOUNDRY = ("FOUNDRY_RESPONSES_URL", "FOUNDRY_MODEL", "FOUNDRY_API_KEY")
RESOURCE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,30}[a-z0-9]$")
REGISTRY = re.compile(r"^[a-z0-9]{5,50}\.azurecr\.io$")
IMAGE = re.compile(r"^[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}|@sha256:[0-9a-f]{64})$")
IDENTITY = re.compile(r"^/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[A-Za-z0-9_.()-]+/providers/Microsoft\.ManagedIdentity/userAssignedIdentities/[A-Za-z0-9_-]+$")


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    subscription: str
    resource_group: str
    location: str
    environment: str
    app: str
    image: str
    min_replicas: int
    registry_server: str
    registry_identity: str
    foundry_url: str
    foundry_model: str
    foundry_key: str
    approved: bool


def load_config(env: Mapping[str, str]) -> Config:
    missing = [key for key in REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise ConfigurationError("Missing configuration: " + ", ".join(missing))
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", env["AZURE_SUBSCRIPTION_ID"]):
        raise ConfigurationError("AZURE_SUBSCRIPTION_ID must be a subscription UUID")
    for name in ("AFTER90_ENVIRONMENT_NAME", "AFTER90_APP_NAME"):
        value = env[name]
        if not RESOURCE_NAME.fullmatch(value) or "--" in value:
            raise ConfigurationError(name + " must be 2-32 lowercase letters, digits or single hyphens")
    if not re.fullmatch(r"[A-Za-z0-9_().-]{1,90}", env["AFTER90_RESOURCE_GROUP"]) or env["AFTER90_RESOURCE_GROUP"].endswith("."):
        raise ConfigurationError("Invalid AFTER90_RESOURCE_GROUP")
    if not re.fullmatch(r"[a-z][a-z0-9]{1,30}", env["AFTER90_LOCATION"]):
        raise ConfigurationError("AFTER90_LOCATION must be a canonical Azure region name")
    image = env["AFTER90_CONTAINER_IMAGE"]
    if not IMAGE.fullmatch(image) or image.rsplit(":", 1)[-1].lower() == "latest":
        raise ConfigurationError("AFTER90_CONTAINER_IMAGE must include a registry and immutable digest or version tag, not latest")
    try:
        minimum = int(env.get("AFTER90_MIN_REPLICAS", "1"))
    except ValueError:
        raise ConfigurationError("AFTER90_MIN_REPLICAS must be 0 or 1") from None
    if minimum not in (0, 1):
        raise ConfigurationError("AFTER90_MIN_REPLICAS must be 0 or 1")
    server, identity = env.get("AFTER90_REGISTRY_SERVER", ""), env.get("AFTER90_REGISTRY_IDENTITY_ID", "")
    if bool(server) != bool(identity):
        raise ConfigurationError("Private ACR requires both AFTER90_REGISTRY_SERVER and AFTER90_REGISTRY_IDENTITY_ID")
    if server and (not REGISTRY.fullmatch(server) or not IDENTITY.fullmatch(identity) or not image.startswith(server + "/")):
        raise ConfigurationError("Private registry/identity configuration is invalid or does not match the image")
    if image.split("/", 1)[0].endswith(".azurecr.io") and not server:
        raise ConfigurationError("ACR image requires a pre-authorized user-assigned registry identity")
    supplied = [bool(env.get(name, "").strip()) for name in FOUNDRY]
    if any(supplied) and not all(supplied):
        raise ConfigurationError("Set all three FOUNDRY variables or leave all unset")
    if all(supplied):
        try:
            url = urlsplit(env[FOUNDRY[0]])
            valid = url.scheme == "https" and url.port in (None, 443) and url.username is None and url.password is None and bool(url.hostname) and any(url.hostname.endswith(suffix) for suffix in (".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com")) and url.path == "/openai/v1/responses" and not url.query and not url.fragment
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError("FOUNDRY_RESPONSES_URL must be a supported HTTPS Azure v1 Responses endpoint")
    return Config(
        env["AZURE_SUBSCRIPTION_ID"], env["AFTER90_RESOURCE_GROUP"], env["AFTER90_LOCATION"],
        env["AFTER90_ENVIRONMENT_NAME"], env["AFTER90_APP_NAME"], image, minimum, server, identity,
        env.get(FOUNDRY[0], ""), env.get(FOUNDRY[1], ""), env.get(FOUNDRY[2], ""),
        env.get("AFTER90_CLOUD_APPROVED", "").lower() == "true",
    )


def arm_parameters(config: Config) -> dict:
    values = {
        "location": config.location, "environmentName": config.environment, "appName": config.app,
        "containerImage": config.image, "minReplicas": config.min_replicas, "maxReplicas": 2,
        "registryServer": config.registry_server, "registryIdentityId": config.registry_identity,
        "foundryResponsesUrl": config.foundry_url, "foundryModel": config.foundry_model,
        "foundryApiKey": config.foundry_key,
    }
    return {"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#", "contentVersion": "1.0.0.0", "parameters": {key: {"value": value} for key, value in values.items()}}


def build_command(config: Config) -> list[str]:
    if not config.registry_server or "@sha256:" in config.image:
        raise ConfigurationError("--build requires a tagged image in an existing approved ACR with pull identity")
    return ["az", "acr", "build", "--subscription", config.subscription, "--registry", config.registry_server.removesuffix(".azurecr.io"), "--image", config.image.split("/", 1)[1], "--file", "Dockerfile", "--only-show-errors", "--output", "none", str(ROOT)]


def deployment_command(config: Config, parameter_path: str) -> list[str]:
    return ["az", "deployment", "group", "create", "--subscription", config.subscription, "--resource-group", config.resource_group, "--name", config.app + "-release", "--mode", "Incremental", "--template-file", str(TEMPLATE), "--parameters", "@" + parameter_path, "--only-show-errors", "--query", "properties.outputs.publicUrl.value", "--output", "tsv"]


def public_plan(config: Config, *, build: bool = False) -> dict:
    if build:
        build_command(config)  # Validate the build combination even in dry-run mode.
    return {
        "status": "dry_run", "cloud_mutations": False, "azure_cli_installed": shutil.which("az") is not None,
        "resource_group": config.resource_group, "location": config.location,
        "environment_name": config.environment, "app_name": config.app,
        "image": config.image, "build_existing_acr": build,
        "template": "infra/azure/main.json", "target_port": 8000,
        "resources_per_replica": {"cpu": 0.5, "memory": "1Gi"},
        "replicas": {"min": config.min_replicas, "max": 2},
        "foundry_configured": bool(config.foundry_key), "registry_identity_configured": bool(config.registry_identity),
        "cloud_approval_recorded": config.approved,
        "operations": (["build_image_in_existing_acr"] if build else []) + ["create_or_update_managed_environment", "create_or_update_container_app"],
        "manual_gates": ["registered_team", "existing_resource_group", "region_quota", "deployment_permissions", "image_public_or_acrpull_identity", "budget_approved", "post_deployment_smoke_and_private_browser"],
        "credentials": "secure temporary ARM parameter file; never command arguments or report fields",
    }


def run_azure(command: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess:
    # Azure diagnostics can echo request bodies or credentials; never forward them.
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)


def apply(config: Config, *, build: bool = False) -> dict:
    if not config.approved:
        return {"status": "blocked", "reason": "cloud_approval_missing", "cloud_mutations": False}
    if shutil.which("az") is None:
        return {"status": "blocked", "reason": "azure_cli_not_installed", "cloud_mutations": False}
    try:
        auth = run_azure(["az", "account", "show", "--subscription", config.subscription, "--query", "state", "--output", "tsv"], timeout=20)
        if auth.returncode or auth.stdout.strip() != "Enabled":
            return {"status": "blocked", "reason": "subscription_auth_not_verified", "cloud_mutations": False}
        group = run_azure(["az", "group", "exists", "--subscription", config.subscription, "--name", config.resource_group, "--output", "tsv"], timeout=20)
        if group.returncode or group.stdout.strip().lower() != "true":
            return {"status": "blocked", "reason": "existing_resource_group_not_verified", "cloud_mutations": False}
        if build:
            result = run_azure(build_command(config))
            if result.returncode:
                return {"status": "failed", "reason": "acr_build_failed", "cloud_mutations": True}
        # The file is private, short-lived and outside the repository; key never
        # appears in argv. ARM marks the three Foundry parameters secureString.
        with tempfile.TemporaryDirectory(prefix="after90-deploy-") as temporary:
            parameters = Path(temporary) / "parameters.json"
            with parameters.open("x", encoding="utf-8") as handle:
                os.chmod(parameters, 0o600)
                json.dump(arm_parameters(config), handle)
            result = run_azure(deployment_command(config, str(parameters)))
        if result.returncode:
            return {"status": "failed", "reason": "arm_deployment_failed", "cloud_mutations": True}
        public_url = result.stdout.strip()
        if not re.fullmatch(r"https://[a-z0-9.-]+\.azurecontainerapps\.io", public_url):
            return {"status": "deployed_unverified", "reason": "public_url_not_validated", "cloud_mutations": True}
        return {"status": "deployed_unverified", "public_url": public_url, "cloud_mutations": True, "next": "Run scripts/smoke_deployment.py against this URL and complete a private-browser walkthrough before claiming release."}
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "azure_command_timeout_state_unknown", "cloud_mutations": "unknown"}
    except OSError:
        return {"status": "failed", "reason": "azure_command_unavailable_state_unknown", "cloud_mutations": "unknown"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Opt in to cloud changes after account, region, permissions and spending approval.")
    parser.add_argument("--build", action="store_true", help="Build the Dockerfile in an existing approved ACR before deployment; dry-run unless --apply.")
    args = parser.parse_args()
    try:
        config = load_config(os.environ)
        plan = public_plan(config, build=args.build)
    except ConfigurationError as error:
        print(json.dumps({"status": "blocked", "cloud_mutations": False, "reason": str(error)}, indent=2))
        return 2
    result = apply(config, build=args.build) if args.apply else plan
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("dry_run", "deployed_unverified") else 1


if __name__ == "__main__":
    raise SystemExit(main())
