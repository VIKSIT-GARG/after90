# After90 remaining release gates

Audit framework for the twelve-phase plan, updated October 25, 2026. See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for final local test and
browser evidence. This
file separates a local implementation from real service and account acceptance.

| Phase | Implemented/prepared work | Evidence required to close the phase |
| --- | --- | --- |
| 1 | Shared contracts, naming, ownership and scope | Owner handoff review; dependent frontend PRs integrated in order |
| 2 | Readiness CLI and explicit real-service probe | Actual Foundry configuration and successful request; registration, subscription rights, region/quota and permitted spend verified |
| 3 | 60-case offline corpus, validated fictional scenarios | Offline evaluation report; live/human quality is not inferred from this |
| 4 | Canonical context and replay-bounded interpretations | Temporal/entity/scoring tests and canonical output inspection |
| 5 | Bounded Foundry selection, controlled rendering, truthful fallback | Offline negative tests plus real Foundry acceptance/usefulness and latency evidence |
| 6 | Ranked/deduplicated story ledger and recap packets | Goal/non-goal coverage, no future claims, coherent recap checks |
| 7 | API/service/cache integration work | Full HTTP suite; paired-mode sharing, TTL/versioning, concurrency/recovery and request-budget tests |
| 8 | Personalized UI, evidence and studio-preview work | Actual desktop/mobile/keyboard browser checks with correct source labels and no stale output |
| 9 | Integrated evaluator and release QA work | Local and public end-to-end checks; measured live-model results and human usefulness review separately recorded |
| 10 | ARM template, safe deploy CLI and runbook | Actual Azure deployment, image pull, real backend Foundry call, public smoke test, private-browser walkthrough and rollback evidence |
| 11 | Team prioritization implemented behind default-disabled build flag | Activate only after phase 10; verify story ordering changes without factual changes |
| 12 | Pitch, technology statement and 110-second storyboard | Final actual-build video, public hosting links, authorized submission and saved receipt |

## Account-dependent gates currently blocked

The execution environment was checked for presence only. It has no Azure CLI,
subscription setting, configured release image, Foundry endpoint/model/key, or
cloud deployment context. This is **not** evidence that the team lacks an account;
it means this environment cannot prove or execute its cloud release.

The account operator must supply private configuration through deployment secrets
and verify registration, permissions, quota/region, image-pull authorization and
budget. The deployment CLI cannot turn absent account access into a completed
phase. It defaults to an offline plan and does not purchase or provision model
access. No real credentials belong in source, screenshots, issue comments or the
submission package.

## Local versus live evidence

- Unit, injected-client and local integration tests establish their recorded
  assertions only; they do not measure live-model accuracy or public uptime.
- Browser automation against the local build establishes tested rendering and
  interaction paths; a public deployment still needs its own walkthrough.
- A successful ARM response returns `deployed_unverified`. Smoke, private-browser
  access, source provenance and Foundry operation must pass before release.
- A demo script or local recording is not a publicly hosted submitted video.
- Development-agent collaboration is not runtime multi-agent orchestration.

## PR integration and approval

The AI work is stacked over the existing frontend PRs. Preserve their dependency
order and resolve review/merge requirements before final main-branch integration.
GitHub rejects an author approving their own pull request; an independent
collaborator must perform that approval when the connected account is the author.
No approval rejection should be presented as a successful review submission.

## Reproduce deployment preparation checks

```sh
python -m pytest tests/test_deploy_azure.py
python scripts/deploy_azure.py
```

A missing-configuration exit 2 with `cloud_mutations: false` is expected in this
environment. See [AZURE_RELEASE.md](AZURE_RELEASE.md) and
[SUBMISSION_PACKAGE.md](SUBMISSION_PACKAGE.md) for concrete operator handoffs.
