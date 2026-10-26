# After90 implementation and acceptance status

**October 26 audit update:** [AI_AUDIT.md](AI_AUDIT.md) records ten open
shortcomings. Live AI acceptance is not signed off; green local tests do not
close the newly reproduced sparse-evidence, pattern-coverage and timeout gaps.

Implementation checkpoint: October 25, 2026. This is the current twelve-phase status. Local software
completion is separate from live-service, account and public-submission proof.

| Phase | Software status | Remaining acceptance action |
| --- | --- | --- |
| 1 Scope/contracts | Implemented, matching Python/TypeScript types | Owner review and existing stacked frontend PR integration |
| 2 Foundry/Azure access | Safe readiness and live probe implemented | Endpoint/model/key, real request, account/quota/budget/registration verification |
| 3 Evaluation corpus | Implemented; 60 offline cases | None for offline preparation |
| 4 Context | Implemented and replay bounded | None for local deterministic service |
| 5 Narrative generation | Implemented, bounded selection and labelled fallback | Live provider acceptance, usefulness and latency |
| 6 Story/recap | Implemented, includes decisive score changes and non-goal patterns | Human usefulness review with real provider |
| 7 API/reliability | Integrated into public HTTP path; cache/recovery/concurrency/budget controls | Real-provider operational verification |
| 8 Personalized UI/overlays | Integrated; desktop/mobile/keyboard and automated accessibility checks passed | Human/screen-reader and public-hosted walkthrough |
| 9 Evaluation | Offline and local HTTP/browser checks implemented and passing | Live model metrics, human assessment and public-hosted checks |
| 10 Azure release | ARM, deploy CLI, tests and operator runbook prepared | Authorized account/image, Azure template validation, deployment, rollback and public smoke proof |
| 11 Optional extension | Favourite-team prioritization implemented/tested behind default-disabled flag | Enable only after core public release gate |
| 12 Submission | Truthful pitch, 110-second storyboard and 28.64-second actual local demo recording prepared | Upload final video to accepted public host, enter demo link, submit and retain receipt |

## What works locally

`bash run.sh` builds the frontend and serves it with FastAPI. Goals, shot surges
and possession changes produce contextual evidence-backed narratives. Fan and
Analyst share facts; the analyst view exposes exact attributed facts/windows.
The studio preview renders a synthetic, timestamped graphic from the selected
insight. Full-time recap includes the equalizer and winning goal, with non-goal
patterns. Source labels accurately distinguish fallback and AI-selected narrative.
No AI prose or model-calculated statistics can replace the canonical evidence.

The API no longer uses the legacy regex wording helper. Both narrative modes
share per-key generation; cache entries expire, failed service calls recover,
concurrent requests are deduplicated and bounded, and temporal availability is
checked before cached data is read. Process budgets are not a global Azure cost
cap. Configure cloud budget controls separately.

## Local quality evidence

See the commands below and CI. The browser runner starts a local server in the
same process namespace, removes model credentials and exercises real Chromium.
It covers goal significance, paired modes, recap, studio graphics, source changes,
keyboard focus, 320/390px overflow and four automated accessibility states. The
optional flag build adds a fifth audited team-priority state with unchanged score.
These checks do not certify complete accessibility or live AI quality.

```sh
python -m pytest
python scripts/evaluate_ai.py
python scripts/evaluate_integrated.py
npm test --prefix frontend
npm run build --prefix frontend
(cd frontend && npx playwright install --with-deps chromium)
python scripts/test_browser.py
```

Actual provider proof: configure private settings and run
`python scripts/evaluate_integrated.py --live --require-foundry`. This fails if
no accepted Foundry selection is observed. Merely passing fallback contracts
never closes the live gate.

## Explicit external blockers

The execution environment has no Azure CLI/account context, authorized release
image or Foundry endpoint/model/key. Registration and permitted spend cannot be
verified from repository code. No cloud provisioning, video-host upload, final
hackathon submission or main-branch merge has been claimed.

GitHub rejected approval of PR #3 with HTTP 422 because the connected account is
its author. Another collaborator must approve it; creating a second identity or
misrepresenting the rejected operation is not a substitute for that review.

Development agents collaborating on code are not runtime multi-agent product
orchestration. The optional feature is a team-priority UI, not an agent swarm.

## Final verification results

- Python suite: **266 passed**.
- Offline corpus: **60/60 passed**.
- Integrated HTTP checks: **8/8 passed**.
- Frontend suite: **12 passed**; production build passed.
- Real Chromium 153: four default-release states and five optional-team-focus
  states passed with **zero automated WCAG A/AA violations**, no runtime errors,
  no horizontal overflow at 320/390px, and preserved activity-seek keyboard focus.
- Optional focus build reordered stories while preserving the score. The final
  build was restored to the default-disabled flag.
- A **28.64-second MP4** records the actual local app flow; it shows labelled
  fallback operation, not a claimed live Foundry connection. It has been provided
  as a separate handoff artifact. Public hosting/submission remain pending.
- Diff and shell syntax checks passed. Independent read-only review found no
  blocking defect in API/cache, async UI/source guards or deployment preparation.
- Live readiness remains **not configured / live not tested**; deployment has
  not been executed. These are explicit acceptance blockers, not test passes.

## Audit remediation follow-up

See `AI_FIX_PLAN.md` for parallel work ownership and dependency order, and the
remediation section of `AI_AUDIT.md` for current finding statuses. Code fixes
AI-03 through AI-10 are implemented with regression coverage. All-type live
Foundry coverage (AI-01) and human editorial-value acceptance (AI-02) remain
required; the new evaluator prepares evidence but cannot substitute for either.

Provider transport runs in a disposable child process to enforce a total deadline
including native DNS. Process startup consumes the request allowance. Budget
limits replenish on a per-process fixed window (`AI_BUDGET_WINDOW_SECONDS`,
default 3600); this is not a shared cloud quota. Snapshot/recap consumers must
respect `possession_available=false` rather than display assumed raw percentages.
