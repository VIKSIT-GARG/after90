# AI and Azure readiness gate

This document records Wave 1, Phase 2 of the AI delivery plan. It is separate from
the older five-phase MVP status in `docs/PHASES.md`. The project uses **Synthetic
match data**. A configured endpoint or a passing mocked test does not prove a live
Foundry connection.

## Current evidence

At the implementation check, none of `FOUNDRY_RESPONSES_URL`, `FOUNDRY_MODEL`, or
`FOUNDRY_API_KEY` was present in the execution environment. Azure subscription and
identity environment variables were also absent, and Azure CLI was not installed.
No live request, Azure provisioning, registration action, deployment, or spending
limit change was performed. The script and mocked transport tests are complete;
the live access gate remains blocked, not completed.

| Gate | Current status | Owner / required evidence |
|---|---|---|
| Foundry connection and strict output support | Blocked: configuration absent | Maryam + Zoya supply private runtime configuration and run the live probe |
| Model region and quota | Unverified | Zoya checks the existing deployment and available quota |
| Azure deployment permission | Unverified | Zoya verifies the intended subscription, resource group, and deployment rights |
| Permitted spend | Unverified | Team agrees a spending ceiling; inspect the actual subscription controls |
| Existing hackathon registration | Unverified | Zoya verifies the team's existing registration/representative record |
| Public Azure application | Not verified | Deploy and smoke-test during the public release phase |
| Production narrative quality | Not evaluated by this probe | Run the evaluation scenarios against the actual generation pipeline |

## Configure privately

The existing backend adapter uses three names:

- `FOUNDRY_RESPONSES_URL`: the full HTTPS Azure OpenAI v1 Responses URL, for example
  `https://YOUR-RESOURCE.openai.azure.com/openai/v1/responses`.
- `FOUNDRY_MODEL`: the deployment name accepted by that resource, not an assumed
  catalog model name.
- `FOUNDRY_API_KEY`: supplied only through local runtime variables or hosting secrets.

The readiness script accepts Azure hosts ending in `.openai.azure.com`,
`.services.ai.azure.com`, or `.cognitiveservices.azure.com`, HTTPS port 443, and
exactly `/openai/v1/responses`. It rejects credentials in URLs, query strings,
fragments, alternate ports, non-Azure hosts, and HTTP. Redirects are disabled so
an API-key request cannot be forwarded to another host. A valid URL shape does
not establish that a particular resource supports Responses or structured output.
Private/custom endpoints and sovereign-cloud domains require a deliberate code
change and review rather than a permissive override.

`.env.example` contains names only. Copy it to `.env` and fill in private local
configuration, then run `bash run.sh`. The startup wrapper explicitly loads the
repository-root `.env` before starting the backend. Existing process variables
always win, and values are parsed without variable interpolation or shell
execution. A missing file preserves the labelled offline fallback; malformed
files fail startup with a sanitized message. Importing backend modules does not
load files. Direct backend or script invocations use their process environment;
use the same explicit wrapper when they should read `.env`:

```sh
.venv/bin/python -m backend.matchlens.env --run .venv/bin/python scripts/check_ai_readiness.py --live --timeout 5
```

Use deployment secret configuration in hosted environments. Do not commit a
populated `.env`.
Azure CLI login and optional `AZURE_*` identity variables are deployment context;
they do not substitute for `FOUNDRY_API_KEY` in the current key-based adapter.

## Run checks

Install the existing backend development requirements first. From the repository
root:

```sh
python scripts/check_ai_readiness.py
python scripts/check_ai_readiness.py --live --timeout 5
```

The default command makes no Foundry request. If Azure CLI is installed it reads
cached account state through `az account show --query state --output tsv` and
reports only whether an enabled cached account exists. It never logs account,
subscription, tenant, model deployment, endpoint, API-key values, model text, or raw
exception messages.

`--live` makes at most one bounded generation request, with no retries and a
400-output-token cap; it can consume the configured deployment's model budget.
The probe derives a real goal and score transition from the checked-in fixture,
requests strict JSON through Responses `text.format`, and checks the returned
insight ID and complete evidence-ID set. A passing probe proves transport,
authentication, schema support, and presence of generated text for that request.
It explicitly leaves semantic quality `not_evaluated`. It is not a substitute for
the production generator's claim validation or full evaluation suite.

## Interpret results

| Report field | Meaning |
|---|---|
| `configuration: not_configured` | At least one required variable is absent or blank |
| `configuration: invalid_configuration` | All variables exist but the endpoint shape is not allowed |
| `configuration: configured` | Required variables and endpoint shape pass local checks only |
| `foundry_live_probe.status: live_not_tested` | No live request occurred; the reason distinguishes missing configuration from no request |
| `foundry_live_probe.status: pass` | The single live response passed the access/schema smoke check |
| `foundry_live_probe.status: fail` | The request failed or its response/evidence did not pass validation |
| `manual_gates: unverified` | Account permissions, spend, registration, quota and public deployment still need explicit evidence |

Exit codes: `0` means configured in offline mode or a passing probe in live mode;
`2` means missing/invalid configuration; `1` means a configured live probe failed.
Save sanitized JSON and the actual deployment/version in a private team record
when the real check is run. Do not relabel stubbed test runs as live proof.

## Relevant Microsoft documentation

- [Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses)
- [Structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
- [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/get-started-existing-container-image)

Before selecting a deployment, verify actual model support, resource region,
quota, access, and pricing in the team's subscription. This implementation does
not select a paid deployment or provision cloud resources.
