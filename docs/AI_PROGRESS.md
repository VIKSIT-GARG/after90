# After90 Waves 1 and 2 completion audit

Wave 1/2 checkpoint: October 24, 2026. Current integrated status (October 25):
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md). These are the new twelve-phase AI delivery phases,
not the original MVP plan or the frontend PR numbers. The checkpoint below records the initial staged work. Phase 7 has now integrated
the bounded services into the public HTTP path; the old helper is test-only.

## Wave 1

### Phase 1: scope, ownership and contracts

- [x] Product naming and bounded core/optional scope recorded in AI_DELIVERY.md.
- [x] Billi/Maryam/Ayesha/Zoya responsibilities and interfaces documented.
- [x] Strict Python and matching TypeScript contracts implemented.
- [x] Fact references, audience frames, source metadata and overlay contract frozen.
- [x] Original PR #1/#2 changes preserved by stacking this work on PR #2's head.
- [ ] Existing frontend PRs merged in order into the intended integration branch.
- [ ] Human owners have reviewed their handoff contracts and accepted the work.

The implementation contract is ready. This work does not silently merge another
owner's open frontend PR or claim their acceptance. The outstanding integration
and human review actions must be closed before final main-branch release.

### Phase 2: Foundry/Azure access

- [x] Safe offline preflight and explicit bounded --live smoke CLI implemented.
- [x] Configuration presence separated from transport/schema proof and quality.
- [x] Endpoint allowlist, no redirect forwarding, response limits and sanitized errors tested.
- [x] Private configuration names and account/access instructions documented.
- [ ] Real Foundry endpoint/model/key configured in the authorized environment.
- [ ] Real structured-output smoke request succeeds and evidence is retained.
- [ ] Registration, subscription permissions, region/quota and spending limit verified by account owner.

Observed environment: all three FOUNDRY_* settings absent; Azure CLI absent;
Azure identity/subscription environment settings absent. Actual live service
proof is **blocked**, not passed. No model/cloud resource was provisioned and no
account or registration status was guessed.

### Phase 3: evaluation preparation

- [x] Sixty named evaluation cases with expected outcomes.
- [x] Golden fixture preserved unchanged.
- [x] Eight validated fictional scenarios including draw, comeback, late winner and sparse evidence.
- [x] Replay/context, contradiction, attribution, unsupported output, failure, mode and recap checks.
- [x] JSON runner distinguishes deterministic assertions and injected selectors.
- [x] Live latency/token/quality metrics and human usefulness remain explicitly unmeasured.

Phase 3's offline preparation gate is complete. Live and human evaluations belong
to phases 5/9 and are not established by these test results.

## Wave 2

Wave 2's offline service implementation was authorized while the external phase
2 gate remained blocked. It has since been integrated by phases 7/8, but this is not a claim of live
Foundry access in the current execution environment.

### Phase 4: evidence and context

- [x] Validated fixture and engine insight are the only factual sources.
- [x] Unknown/future insights and invalid replay minutes rejected.
- [x] Original moment score transitions retained during later inspection.
- [x] Goal significance, attributed shot windows and possession deltas implemented.
- [x] Unsupported tracking/tactics/chance-quality claims represented as limitations.
- [x] Context determinism, attribution, temporal bounds and mutation-isolation tests.

Phase 4's service gate is complete.

### Phase 5: generation, validation and fallback

- [x] Bounded model selection with a packet-specific structured-output schema.
- [x] Selected facts and required support closure validated.
- [x] Fan/Analyst sentences rendered from authoritative facts and approved frames.
- [x] Arbitrary provider prose, negation/contradiction strings and extra fields rejected.
- [x] Timeout/refusal/malformed/service-failure handling with safe fallback metadata.
- [x] Source provenance distinguishes real Foundry, injected selection and deterministic fallback.
- [x] Offline preview cannot call Foundry even if credentials exist.
- [x] Model/prompt metadata and bounded output limits implemented.
- [ ] Real Foundry output evaluated for useful editorial selection, response acceptance and latency.

The model selects evidence and framing; wording is controlled server rendering.
This deliberately does not claim unrestricted AI prose or perfect semantic
validation of arbitrary text. Offline implementation is complete; live acceptance
is **blocked by phase 2**. Phase 7 now uses the new bounded service for the public API; the legacy regex
helper remains only for historical helper tests.

### Phase 6: story ledger and recap inputs

- [x] Canonical goals and non-goal patterns included in a deterministic ledger.
- [x] Overlapping same-team/type patterns grouped with all source IDs retained.
- [x] Representative metric window kept separate from aggregate group coverage.
- [x] Stable ranking, chronological output and all-goal retention.
- [x] No future evidence or final-result labels in live ledgers.
- [x] Winning-goal attribution only available at full time.
- [x] Recap packet contains final facts, selected stories, goal minutes and limitations.
- [x] Empty/goalless, overlapping-window and replay checks.

Phase 6's deterministic service gate is complete.

## Remaining phases

| Phase | Remaining work | Dependencies |
| --- | --- | --- |
| 7 | Wire new services into HTTP endpoints; versioned caches, in-flight deduplication, lock scope, fallback expiry, request budgets, API tests | 5/6 implemented; phase 2 for real service validation |
| 8 | Connect rich audience views and evidence; studio overlay preview; keyboard/mobile/browser verification | 1/5 contracts and generation |
| 9 | End-to-end deployed/real-model evaluation, human usefulness, latency/usage, browser flows, failure recovery and baseline comparison | 3/7/8 |
| 10 | Public Azure deployment, private-browser smoke check, server credentials, cost controls, rollback and service availability | 9; account access |
| 11 | Optional single extension only after core release | 10 |
| 12 | Actual-build video under two minutes, accurate pitch, public links, submission and receipt | 10 for recording; preparation may begin earlier |

## Reproduce the checks

```sh
python -m pytest
python scripts/evaluate_ai.py
python scripts/check_ai_readiness.py
python scripts/preview_ai.py --insight-id goal-e072 --minute 29
python scripts/preview_ai.py --recap
npm test --prefix frontend
npm run build --prefix frontend
```

Readiness exits 2 when unconfigured; this expected result is an external blocker,
not a test failure or proof of connectivity. Use --live only in an authorized
configured environment. No credentials should be pasted into source or reports.

## Validation recorded for this implementation

- Full Python suite: **206 passed** (includes the existing application tests).
- Offline evaluation corpus: **60/60 passed**; live metrics remain unmeasured.
- Frontend regression suite: **5 passed**.
- TypeScript/production frontend build: **passed**.
- Additional replay sweep: **472 narrative renderings across all 91 minutes**,
  with evidence cutoffs and full-time-only result labels checked.
- Diff whitespace check: **passed**.
- Foundry readiness: **not configured / live not tested**, including an explicit
  --live preflight that correctly declined to call without configuration.
- Independent code review corrected provider-schema compatibility and recap
  selection issues before these checks. These results are offline evidence; they
  do not establish visual/browser, live-model, account or deployed-Azure gates.
