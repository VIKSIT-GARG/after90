# AI audit remediation plan

October 26, 2026. Based on AI_AUDIT.md findings AI-01 through AI-10. The original
finding descriptions remain evidence; closure requires tests and acceptance proof.

## Workstreams and order

| Stage | Parallel workstream | Findings | Exit evidence |
| --- | --- | --- | --- |
| 1 | A: evidence and story selection | AI-03/04 | Empty/sparse percentage qualification; high-goal stories retain patterns |
| 1 | B: transport and provider telemetry | AI-05/06 | Hard monotonic total deadline with cancellation; safe usage/model/attempt metadata |
| 1 | C: budget recovery | AI-07 | Fixed time window, atomic replenishment, visible non-secret budget health |
| 1 | D: evaluation and baseline comparison | AI-01/02 | All-type uncached evaluation, strict coverage gate, paired baseline/reviewer package |
| 1 | E: rendering, UI and setup | AI-08/09/10 | Meaningful recap framing, bounded display names, sparse UI states, safe explicit .env startup |
| 2 | Integrate A/B/C/D/E | All | Public response contracts, matching TypeScript types and full regression suite |
| 3 | Independent re-audit and publish | All | Reproduce original defects; negative transport tests; build and CI |
| 4 | Account-dependent acceptance | AI-01/02 | Actual Foundry all-type run and human preference/usefulness review |

Stages 1 workstreams can proceed simultaneously after agreeing telemetry and
availability interfaces. D can prepare corpus/coverage logic while B is written,
but its integrated telemetry checks depend on B. UI E depends on A's evidence
availability and the API flag. Stage 2 waits for all code workstreams; stage 3
waits for stage 2. Stage 4 requires private service configuration and a reviewer.

No stage fabricates live model success. The safe bounded narrative design stays
in place; the model chooses evidence/framing and code renders authoritative facts.
A blind comparison package enables measurement without falsely claiming that
an automated textual difference proves user benefit.

## Shared additive fields

- `GenerationMetadata.provider_attempted`: whether the real provider transport
  was attempted. Injected selectors never establish this proof.
- `GenerationMetadata.provider`: optional ProviderTelemetry with response/request
  identity, actual returned model, token usage and provider request wall time.
- `possession_available`: explicit boolean on snapshot/recap responses; the recap
  evidence packet also carries numeric 0/1 as a selected availability fact.
- Budget health reports fixed-window, per-process scope and replenishment timing.

The public API's existing fields remain compatible. Provider wall time is never
labelled pure inference latency. Account credentials stay private and public
health does not reveal endpoint, tenant, key or model deployment identifiers.

## Completion checkpoint

Parallel implementation streams are complete. Integration includes Python/TS
contract alignment and the API handoff sample. Re-audit closes the eight code
findings subject to the documented offline scope. Account-dependent live testing
and human ratings remain the final sequential acceptance phase; they cannot run
successfully before a configured deployment and reviewers are available.
