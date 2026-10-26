# After90 Azure release runbook

Status on October 25, 2026: the template and deployment CLI are implemented and
offline-tested. This execution environment has no Azure CLI, subscription context,
Foundry credentials or release image configured. **No public Azure release or
live Foundry proof is claimed.**

## What is ready

- `infra/azure/main.json`: Container Apps environment and application, HTTPS
  ingress on port 8000, versioned image, bounded replicas and health probes.
- `scripts/deploy_azure.py`: default offline JSON plan; explicit `--apply` for
  deployment, and optional `--build` for an existing approved ACR.
- Server-only Foundry settings and private temporary ARM parameter handling.
- Sanitized CLI failures and statuses that retain post-deployment verification.
- Existing container build, application smoke check and rollback path.

## Required existing account resources

The release operator verifies team registration, subscription permissions, region
and quota, and the permitted budget. The script requires an existing resource
group and an image that Azure can pull. It does not create login state, purchase
model capacity, assign registry roles or create an account.

Supply these values privately in the release shell; the repository contains
names and examples only:

| Variable | Value |
| --- | --- |
| `AZURE_SUBSCRIPTION_ID` | Existing subscription UUID |
| `AFTER90_RESOURCE_GROUP` | Existing approved resource group |
| `AFTER90_LOCATION` | Supported canonical region, e.g. `southindia` |
| `AFTER90_ENVIRONMENT_NAME` | Dedicated Container Apps environment name |
| `AFTER90_APP_NAME` | Dedicated app name |
| `AFTER90_CONTAINER_IMAGE` | Actual published image with version tag or digest; never `latest` |
| `AFTER90_MIN_REPLICAS` | `1` for a warm demo; `0` only if cold starts are acceptable |
| `AFTER90_CLOUD_APPROVED` | `true` only after the operator verifies budget and permissions |

For private ACR, also set `AFTER90_REGISTRY_SERVER` and
`AFTER90_REGISTRY_IDENTITY_ID`. The identity must already have pull access to that
registry and the image must use the same registry host. `--build` can build into
this existing ACR; it does not create the ACR or its permissions.

For real Foundry selection, supply all three server settings together:
`FOUNDRY_RESPONSES_URL`, `FOUNDRY_MODEL`, and `FOUNDRY_API_KEY`. The URL is the
full HTTPS Azure `/openai/v1/responses` endpoint and the model is the deployment
name. Leave all three absent for a clearly labelled template fallback.

## Build, plan and verify before release

Run the affected tests and build from a clean checkout:

```sh
python -m pytest
python scripts/evaluate_ai.py
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
docker build -t after90:release-check .
docker run --rm -p 127.0.0.1:8000:8000 after90:release-check
```

In another shell, run `python scripts/smoke_deployment.py http://127.0.0.1:8000`.
Publish the built image to the reviewed registry with a unique revision tag or
an immutable digest. Record the previous working image before updating an app.

Inspect the offline plan; neither command contacts Azure:

```sh
python scripts/deploy_azure.py
python scripts/deploy_azure.py --build
```

The second command is only valid for a version-tagged image in the configured
existing ACR. Missing configuration returns exit 2 and `cloud_mutations: false`.
The report never contains the Foundry key, full endpoint or model setting.

Before applying, validate the ARM template with the account's Azure CLI using
`az deployment group validate` and review its `what-if` result. These are Azure
operations requiring the operator's access; offline tests cannot establish their
outcome. If Foundry is configured, use a private parameter file, not inline keys,
for manual ARM commands. Prefer the script's private-file handling for the actual
apply path.

Once account prerequisites are verified:

```sh
python scripts/check_ai_readiness.py --live
python scripts/deploy_azure.py --apply
# Or build in the existing approved ACR, then deploy:
python scripts/deploy_azure.py --apply --build
```

An explicit apply checks cached subscription auth and existing resource-group
presence. The script writes ARM parameters into a private temporary directory,
sets the file to mode 0600 before writing secrets, and deletes it on success or
failure. No key is put in process arguments or printed logs. Azure diagnostics
are captured, not forwarded, because provider errors may include request data.
Do not use debug output or commit a parameter file containing real values.

## Meaning of results

| Result | Meaning |
| --- | --- |
| `dry_run` | Offline plan only; no cloud access or mutation |
| `blocked` | Missing configuration/account/approval; no deployment performed |
| `failed` | A requested Azure command failed; inspect Azure separately, without exposing secrets |
| `deployed_unverified` | Azure returned an app URL; functional public release is still unverified |

The template uses Single revision mode and can update an existing dedicated app.
Bounded replicas are not a monetary spending cap: the account operator must apply
and monitor the approved Azure budget and usage alerts separately.

## Public release acceptance

After a deployment returns its actual URL:

1. Run the application smoke script against that URL.
2. Run the integrated evaluator against that URL, using live mode only when
   real model use is intended and budgeted.
3. Open the site in a private browser without team login.
4. Verify synthetic label, replay/reset, Fan/Analyst distinction, evidence,
   studio preview, full-time recap and model failure behaviour.
5. Confirm the deployed backend can call Foundry and label real selection as
   `foundry`; configuration alone does not prove this.
6. Record revision, image digest/tag, prompt/model identifiers, date and test
   outcome without credentials. Keep the demo accessible through judging.

Only then replace `deployed_unverified` with a verified release statement in the
submission materials.

## Rollback and shutdown

Save the previously verified image digest/tag. To roll back, set
`AFTER90_CONTAINER_IMAGE` to that image, inspect the offline plan, then apply the
same template under the reviewed account settings. Repeat smoke and private
browser checks; never assume a successful ARM operation establishes app health.
Do not delete a shared resource group. After judging, the account owner can remove
the dedicated app/environment and review any retained registry or model costs.

## Reference and validation limits

The pinned resources follow Microsoft's
[Container App contract](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/containerapps)
and [managed environment contract](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/managedenvironments).
Azure documents
[resource-group validate and what-if operations](https://learn.microsoft.com/en-us/cli/azure/deployment/group).
Offline tests establish secret handling, command gating, validation rules, JSON
structure and bounded resources. ARM semantic validation, image pull, regional
quota, cost and public reachability still require the authorized Azure account.
