# After90 Azure release template

`main.json` targets the stable `Microsoft.App@2025-01-01` resource contract.
It creates/updates one Consumption managed environment and one Container App in
an **existing** resource group. It does not create a subscription, resource group,
registry, model deployment, identity or role assignment.

The app serves the React build and FastAPI on port 8000, uses HTTPS ingress,
0.5 CPU/1 GiB per replica, one warm replica by default and at most two replicas.
Startup, readiness and liveness use `/api/health`. Application log export is
`none` to avoid implicitly creating a billable Log Analytics workspace; select
and configure a reviewed logging destination before a production rollout.

Supply a public versioned image or an existing ACR image and pre-authorized
user-assigned identity with image-pull permission. The API key is an ARM
`secureString` and a Container Apps secret. No browser-side environment or bundle
receives that key. The model and endpoint parameters are also marked secure so
that raw deployment diagnostics do not echo connection details.

Use `python scripts/deploy_azure.py` for offline planning and consult
[the release runbook](../../docs/AZURE_RELEASE.md) before cloud changes.
The offline tests check the template's JSON and application invariants. They do
**not** substitute for Azure Resource Manager validation, regional availability,
image-pull checks or a successful deployment.

Official resource references:

- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/containerapps
- https://learn.microsoft.com/en-us/azure/templates/microsoft.app/2025-01-01/managedenvironments
- https://learn.microsoft.com/en-us/cli/azure/deployment/group
