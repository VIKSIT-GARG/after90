# Connect a real Foundry deployment to After90

This guide starts with an Azure account and ends with a deployed model connected
to After90's existing backend Responses adapter. All match data stays synthetic.
The setup creates **Azure OpenAI in Microsoft Foundry** (a Cognitive Services
`OpenAI` resource and a model deployment). It does not create a Foundry Agent
Service project, provision agents, or deploy the website.

The script is an **offline plan by default**. No Azure action was performed while
implementing this tooling. Tests exercise mocked command responses; they do not
prove resource deployment, account quota or live model quality.

## 1. Choose a compatible model and region

In the Foundry/Azure model catalog for your subscription, confirm:

- The exact model **name and version** supports the Responses API and strict
  JSON-schema output used by After90.
- That version is available in the selected region and deployment SKU.
- Your subscription has the required quota and permission to create the resource
  and deployment. Student subscriptions and regional quotas can differ.
- The actual model/SKU pricing fits an agreed spending ceiling. Capacity units
  vary by model and deployment type; `1` does not mean one token or one dollar.

Microsoft's Responses documentation lists `gpt-4.1-mini`, version `2025-04-14`,
as supported at the time of this implementation. That is a **candidate to check**,
not a guarantee of present account/region availability or a promised quality or
price advantage. The script deliberately requires an explicit model version and
never guesses or selects a model for your subscription. Use the catalog's actual
values. Review [structured-output support](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)
and [model/region availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure).

The template permits consumption deployment SKUs `Standard`, `GlobalStandard`
and `DataZoneStandard`, subject to model support. It excludes provisioned-throughput
SKUs from this demo setup. Choose data residency and regional behavior deliberately.
An application request quota or Azure budget alert is **not** a hard cloud billing
cap. Configure account spending controls independently.

## 2. Prepare a non-secret plan

From the repository root, with the documented Python dependencies installed:

```sh
cp infra/azure/foundry.config.example.env "$HOME/after90-foundry.env"
```

Edit that private local file. Supply your subscription UUID, resource group,
canonical region, globally available lowercase resource/custom-subdomain name,
deployment name, model name/version, deployment SKU and capacity. The example's
`YOUR-*` values must be replaced. Keep `AFTER90_FOUNDRY_APPROVED=false` during
planning. Leave `AFTER90_FOUNDRY_CREATE_GROUP=false` to require an existing group;
set it to `true` only if the named group should be created when absent.

```sh
.venv/bin/python -m backend.matchlens.env \
  --env-file "$HOME/after90-foundry.env" \
  --run .venv/bin/python scripts/setup_foundry.py
```

The plan shows the intended resource, exact model version/SKU/capacity,
operations, endpoint shape and remaining checks. It does not contact Azure,
require an API key, create a resource or prove name/quota availability. Existing
process environment variables take precedence over this file; use a clean shell
if a plan differs from the file you edited.

## 3. Apply the reviewed plan in your Azure account

Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
and sign in using Microsoft's interactive flow on your machine:

```sh
az login
```

Use the intended public Azure subscription. The script supplies the subscription
explicitly to every subscription operation and does not switch your default
account. It checks that the selected subscription is enabled, the active cloud
is `AzureCloud`, and `Microsoft.CognitiveServices` is already registered. If the
provider is unregistered, an authorized subscription operator must register it;
the setup script does not change subscription-wide provider registration.

After reviewing cost, region, model/strict-output support and quota, set
`AFTER90_FOUNDRY_APPROVED=true` in your local configuration. Apply explicitly:

```sh
.venv/bin/python -m backend.matchlens.env \
  --env-file "$HOME/after90-foundry.env" \
  --run .venv/bin/python scripts/setup_foundry.py --apply
```

`--apply` first checks account/cloud/provider/group state. If allowed, it creates
a missing resource group, validates the ARM deployment, then creates or updates
the resource and model deployment in **Incremental** mode. It never deletes
unrelated resources, logs in, retrieves API keys or assigns roles. Model versions
are pinned with `NoAutoUpgrade`; monitor retirement and update deliberately.
The public HTTPS data endpoint and local API-key authentication are enabled for
After90's current backend adapter. Credentials are still required to call it.
Private endpoints, managed-identity authentication and sovereign-cloud domains
need a separately reviewed configuration and adapter change.

A failed Azure operation produces a sanitized reason code. Review deployment
history in your own portal for detailed diagnostics. A newly created group may
remain if later validation fails; `cloud_mutations=true` reports that partial
state. The script never deletes it automatically. A successful deployment report
contains only the expected non-secret endpoint and deployment name, and still
marks `live_inference=not_tested`.

## 4. Connect the application privately

Copy the successful report's application settings into the repository's local
`.env` (copy `.env.example` first if needed):

```dotenv
FOUNDRY_RESPONSES_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/responses
FOUNDRY_MODEL=YOUR-DEPLOYMENT-NAME
FOUNDRY_API_KEY=YOUR-PRIVATE-RESOURCE-KEY
```

`FOUNDRY_MODEL` is your **deployment name**, not necessarily the catalog model
name. Obtain the key privately from that resource's Keys and Endpoint page in
Azure/Foundry. Do not paste it into chat, Git, screenshots or browser code. The
setup script never prints or stores it. For hosted applications, use the existing
backend secret mechanism described in [AZURE_RELEASE.md](AZURE_RELEASE.md).

Start the application with `bash run.sh`. That wrapper explicitly reads `.env`
for the backend. The source indicator changes only after a real accepted provider
response; setting environment variables alone does not establish a live AI call.

## 5. Verify live behavior and usefulness

Use the same explicit environment loader for direct scripts:

```sh
.venv/bin/python -m backend.matchlens.env --run \
  .venv/bin/python scripts/check_ai_readiness.py --live --timeout 5

.venv/bin/python -m backend.matchlens.env --run \
  .venv/bin/python scripts/evaluate_live_ai.py --live --require-foundry \
  --output live-report.json --review-output blinded-review.jsonl
```

These live commands can incur model usage. The uncached evaluator requires
accepted actual Foundry results across every supported insight type and recap;
it cannot pass from an injected test client or a single successful goal. Review
latency, failure reasons and optional usage telemetry; then collect human ratings
on the blinded text pairs to establish editorial value. Keep the full report's
A/B mappings from reviewers. See [AI_EVALUATION.md](AI_EVALUATION.md).

## Sources and implementation contract

The resource and deployment use stable ARM API version `2025-06-01`. The template
is intentionally parameterized rather than claiming that one model/region/SKU
combination works in every subscription.

- [Resource schema: Microsoft.CognitiveServices/accounts, 2025-06-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts)
- [Deployment schema: accounts/deployments, 2025-06-01](https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/2025-06-01/accounts/deployments)
- [Create Azure OpenAI resources and deploy models](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/create-resource)
- [Responses API: supported models, regions and authentication](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses)
- [Strict structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs)

Offline verification: `python -m pytest -q tests/test_setup_foundry.py`. Coverage
includes missing/invalid configuration, no-network default plans, subscription
and provider preflight, explicit group creation, validation-before-deploy,
restricted temporary files, output validation, sanitized failures and absence of
key retrieval. This is setup-orchestration evidence, not live cloud acceptance.

## Connect privately with the guided setup

After deploying the model, run `.venv/bin/python scripts/connect_foundry.py`.
Enter the Azure resource endpoint and deployed-model name, then paste the key
into the hidden local prompt. The wizard normalizes the resource URL, preserves
other environment settings and atomically saves a private `.env`. Keys are never
passed on the command line or printed. Use `--replace` to update a connection.

Check configuration without making a model call:

```sh
.venv/bin/python scripts/connect_foundry.py --check
```

Explicitly run all-context narrative and Copilot evaluation (up to 19 provider requests; consumes model usage):

```sh
.venv/bin/python scripts/connect_foundry.py --check --verify
```

Existing process variables override `.env`, matching normal startup. A successful
configuration check proves only valid configuration presence; live evaluation
and human review establish operational and editorial acceptance.
