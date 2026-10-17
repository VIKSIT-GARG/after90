# MatchLens deployment runbook

**Synthetic match data.** MatchLens replays a fixed fictional fixture. The container bundles the React build, Python API, and `data/demo_match.json`; the browser calls `/api` on the same origin. The container listens on port 8000 and runs as a non-root user. This runbook prepares an Azure Container Apps public demo; it is not a record of an actual deployment.

## Release gates before spending or publishing

1. Complete registration by **October 20, 2026 at 12:00 p.m. Pacific Time** and submit by **October 27, 2026 at 11:59 p.m. Pacific Time**. The [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) require a public GitHub repository, a public demonstration video shorter than two minutes on YouTube, Vimeo, Facebook Video, or Youku, and access to a working project for judging. Confirm the chosen category and team representative on the submission form. Keep the demo available free of charge and without restriction through the judging period ending **November 10, 2026 at 11:59 p.m. Pacific Time**. The dates in the project plan are internal targets.
2. Confirm an Azure subscription, deployment permission (the [Microsoft quickstart](https://learn.microsoft.com/en-us/azure/container-apps/quickstart-repo-to-cloud) calls for Contributor or Owner), region availability, remaining credits, and an agreed spend limit with the account owner. `az containerapp up` may create a resource group, Container Apps environment, Log Analytics workspace, and registry. Check each resource's cost and the [Container Apps billing rules](https://learn.microsoft.com/en-us/azure/container-apps/billing) first. Consumption has monthly free grants, but usage beyond them and other resources can be billed. Scale-to-zero can cause a cold start during a live demo.
3. Confirm the image works locally and that the API serves the built frontend at `/`. Both the public smoke check and a private-browser walkthrough must pass before sharing the URL.
4. Decide whether Foundry is enabled. The default template fallback needs no Foundry credentials. Only claim a live Foundry integration after a real, evidenced request succeeds. Keep all credentials out of the browser bundle, repository, screenshots, and recording.

## Build and verify locally

From the repository root, with Docker, Python 3, and available port 8000:

```sh
python3 -m pip install -r backend/requirements-dev.txt
python3 -m pytest
cd frontend && npm ci && npm run build && cd ..
docker build -t matchlens:local .
docker run --rm --name matchlens-local -p 127.0.0.1:8000:8000 matchlens:local
```

In another terminal:

```sh
python3 scripts/smoke_deployment.py http://127.0.0.1:8000
```

The smoke command checks `/api/health`, synthetic snapshots at minutes 0 and 90, the golden final score, both insight and recap modes, and the React HTML and JavaScript asset at `/`. It exits nonzero on a missing, malformed, or timed-out response. It does not execute browser JavaScript, so also open the page and test replay, insight evidence, Fan/Analyst wording, full-time recap, and the visible **Synthetic match data** label. The CI workflow repeats tests, frontend build, image build, and container smoke check on pushes and pull requests.

## Deploy to Azure Container Apps

Use the repository root as the source. Install the [Azure CLI and Container Apps extension](https://learn.microsoft.com/en-us/azure/container-apps/containerapp-up), then sign in and select the approved subscription. The account owner chooses names and an available region. These commands create cloud resources and should run only after the gates above are met.

```sh
az login
az account set --subscription '<approved-subscription-id>'
az extension add --name containerapp --upgrade
az containerapp up \
  --name matchlens-demo \
  --resource-group matchlens-demo-rg \
  --location '<approved-region>' \
  --environment matchlens-demo-env \
  --source . \
  --ingress external \
  --target-port 8000
```

Microsoft documents [`az containerapp up --source .`](https://learn.microsoft.com/en-us/azure/container-apps/containerapp-up) for building a root Dockerfile and deploying local source. [External ingress with target port 8000](https://learn.microsoft.com/en-us/azure/container-apps/ingress-how-to) makes this one container's page and API publicly reachable. Use the returned URL, or retrieve the hostname:

```sh
az containerapp show \
  --name matchlens-demo \
  --resource-group matchlens-demo-rg \
  --query properties.configuration.ingress.fqdn \
  --output tsv
python3 scripts/smoke_deployment.py 'https://<returned-hostname>' --timeout 15
```

Set replica limits only after deciding the cost and demo latency tradeoff with the account owner; the [CLI supports `--min-replicas` and `--max-replicas`](https://learn.microsoft.com/en-us/cli/azure/containerapp). A minimum of zero reduces idle compute but may make the first request slow. Review the Container App's revision status, logs, and resource usage in Azure. If health probes need tuning, use `/api/health` for HTTP checks; [Container Apps supports startup, liveness, and readiness probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes).

### Optional Foundry configuration

The backend adapter expects these **runtime** names when a verified Foundry deployment is available:

| Variable | Meaning |
|---|---|
| `FOUNDRY_RESPONSES_URL` | Full Responses endpoint URL |
| `FOUNDRY_MODEL` | Deployed model name |
| `FOUNDRY_API_KEY` | Secret API key |

Enter `FOUNDRY_API_KEY` as a Container Apps secret in the Azure portal, then set an environment variable referencing it. Set the endpoint URL and model as runtime environment variables. [Container Apps secret references](https://learn.microsoft.com/en-us/azure/container-apps/environment-variables) use `secretref:<secret-name>` and environment variable changes create a new revision. For example, after creating a portal secret named `foundry-api-key`:

```sh
az containerapp update \
  --name matchlens-demo \
  --resource-group matchlens-demo-rg \
  --set-env-vars \
    FOUNDRY_RESPONSES_URL='<approved-full-responses-url>' \
    FOUNDRY_MODEL='<deployed-model-name>' \
    FOUNDRY_API_KEY=secretref:foundry-api-key
```

Do not put a real key in a CLI argument, source file, workflow variable, or frontend `VITE_` variable. The fallback must continue working if Foundry is unconfigured or unavailable. Verify the returned explanation `source` before describing text as model generated. Foundry access and cost must be approved separately from Container Apps.

## Public acceptance and handoff

- Run the smoke script against the **public HTTPS URL**, then open that URL in a private browser with no team login. Try desktop and mobile widths.
- Replay from minute 0, pause and reset, jump to minute 29 for the `goal-e072` card, inspect its supporting event IDs, switch Fan/Analyst, and reach full time. Confirm the final score is Northstar Quay 2, Copper Vale 1 and the recap agrees with the API.
- Record the actual public build using [DEMO_SCRIPT.md](DEMO_SCRIPT.md), verify the exported video is under two minutes, upload it to a permitted public video host, and test the public repo, app, and video links in a private session. Record the actual services used in the final pitch and README. Keep copyrighted music, third-party marks, and unlicensed footage out of the submission.
- If deployment fails, use `az containerapp logs show --name matchlens-demo --resource-group matchlens-demo-rg --type system --tail 50` and the app logs in the portal. Do not publish a URL that only passes an API smoke check while the browser experience is broken.
