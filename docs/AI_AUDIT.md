# AI readiness audit — October 26, 2026

**Verdict: NOT signed off as fully working live AI.** The bounded AI integration
and labelled fallback pass the current offline suite, but live model acceptance
is blocked and the additional probes below expose uncovered behaviour.

Audited application commit: `c590301b9a8aaf007f7bec1b9fb23760797ef3b1`.
Scope: public API, context, narrative selection/rendering, story/recap, provider
transport, cache/budget behaviour, telemetry and setup/evaluation documentation.
Two independent read-only reviews supplemented the root-agent checks. No runtime
fixes are included in this audit; all findings below are **OPEN**.

## Evidence and limits

- Fresh full suite: **266 passed**, with one framework deprecation warning.
- Fresh offline corpus: **60/60 passed**.
- Explicit live preflight: **not_configured / live_not_tested**; all three
  Foundry settings absent. No request could be made to a real model.
- Azure CLI/account context absent. Public deployment and human usefulness remain
  unverified. Prior browser/CI passes do not establish model quality.
- Empty-evidence, high-scoring recap, inert-frame and long-name probes used local
  synthetic fixtures. Timeout probe used only a local test server with an
  in-memory test override; the production endpoint allowlist was not changed.
- No P0 defect was found in the reviewed golden-fixture path. This is a scoped
  audit, not a guarantee that the entire application is defect-free.

## Findings register

| ID | Priority | Kind | Status | Finding |
| --- | --- | --- | --- | --- |
| AI-01 | P1 | Release acceptance blocker | OPEN / BLOCKED | Real Foundry operation and all-type live coverage unproved |
| AI-02 | P1 | Product acceptance gap | OPEN | The model's editorial value over deterministic fallback is unmeasured |
| AI-03 | P2 | Evidence-presentation defect | OPEN | Empty event record renders unqualified 100–0 possession |
| AI-04 | P2 | Story coverage defect | OPEN | Six or more goals can remove every non-goal pattern from selected recap input |
| AI-05 | P2 | Transport deadline defect | OPEN | Three-second socket timeout is not a three-second total deadline |
| AI-06 | P2 | Observability gap | OPEN | Provider usage, actual model identity and independent attempts are not retained |
| AI-07 | P2 | Operational limitation | OPEN | Process-lifetime budget exhaustion keeps AI on fallback until restart |
| AI-08 | P3 | Inert model control | OPEN | Recap analyst_frame has no presentation effect |
| AI-09 | P3 | Accepted-input robustness defect | OPEN | Long valid team names can make fallback rendering raise before the guarded provider block |
| AI-10 | P3 | Setup documentation inconsistency | OPEN | Copying .env does not configure the running process automatically |

P1 denotes acceptance work needed before claiming the AI is complete. It does
not mean every P1 item is an exploitable code bug. P2 items should be addressed
before broad/sustained deployment. P3 items affect polish or non-golden inputs.

### AI-01 — Live connection and coverage

The environment lacks FOUNDRY_RESPONSES_URL, FOUNDRY_MODEL and FOUNDRY_API_KEY.
The current live runner exercises the first goal in Fan/Analyst mode and a recap
(`scripts/evaluate_integrated.py`, `_evaluate`), not shot-surge/possession contexts
or the complete corpus. The two goal mode responses can share a cached result.
`--require-foundry` correctly means **at least one** accepted Foundry response;
one success and two fallbacks still pass that particular requirement. It does
not certify that every AI task works.

**Close when:** real production generation is exercised for all supported insight
types and recap, both audience outputs are inspected, independent attempt and
fallback counts are recorded, and usefulness/latency acceptance is documented.
Run the readiness probe first, then extend all-type live evaluation. Never treat
an injected result or a template as proof of live AI.

### AI-02 — Implemented AI responsibility and usefulness

`narrative.py` deliberately asks the model to select approved facts, an approved
interpretation and audience frames. Factual sentences and story ranking are
rendered/calculated by code. This is a legitimate bounded AI design, but it is
**AI-selected, server-rendered narrative**, not unrestricted AI-written football
analysis or runtime multi-agent reasoning. Several contexts have a single
supported interpretation; useful model influence therefore needs demonstration.

**Close when:** representative real-model selections are compared with the
all-facts deterministic baseline by a reviewer for relevance, concision and
viewer value. Preserve the safety boundary; do not introduce free prose solely
to make an AI claim. Keep pitch/source labels consistent with actual behaviour.

### AI-03 — Sparse possession is presented too confidently

`story.py:build_recap_context` includes possession totals for every fixture.
`narrative.py:render_narrative` prints them without an availability/assumption
qualifier. The empty scenario has no event evidence, yet the recap ends:

> Possession: Northstar Quay 100%, Copper Vale 0%.

The arithmetic follows the explicit initial-holder assumption; the defect is
presenting that allocation as an unqualified observed statistic when evidence
is absent. Existing empty-case tests check limitations, not this qualification.

**Close when:** insufficient event evidence produces unavailable or explicitly
assumption-derived possession, consistently in facts, prose and UI; add an
assertion on the actual empty/sparse recap text and evidence availability.

### AI-04 — Goals consume the entire pattern allowance

`story.py:build_story` starts with every goal and calculates
`remaining = max(0, max_moments - len(goals))`. At six goals with the default cap,
no non-goal pattern can be selected, even when supported patterns exist.

A validated seven-goal golden variant selects seven goal moments only, while its
available ledger includes both shot_surge and possession_swing. Retaining every
goal is useful, but should not eliminate the deeper story entirely.

**Close when:** reserve an independent allowance for important pattern types or
summarize their omission explicitly; preserve goal provenance and bounded prose.
Test a validated high-scoring fixture with both pattern types.

### AI-05 — The provider timeout is an inactivity timeout

`narrative.py:_call_foundry` uses urllib `open(..., timeout=3)` followed by a body
read. That timeout applies to socket inactivity, not an overall monotonic deadline.
A local server sending four body chunks one second apart returned successfully
in **4.01 seconds** despite TIMEOUT_SECONDS=3. A sufficiently slow body can retain
an owner request/provider slot much longer. Single-flight waiter timeout does not
cancel that owner.

**Close when:** enforce a total request/read deadline and cancel/close the
transport at expiry; retain deterministic fallback. Test both stalled and
continuously trickling responses, not only an injected TimeoutError.

### AI-06 — Provider telemetry is discarded

The response parser retains selection JSON but drops returned usage and response
identity; metadata.model_version is the configured deployment name rather than
the returned provider model revision. The evaluator explicitly reports provider
inference latency as not_measured and response-level fallback rates that can
include cache hits. These are honest limitations, but insufficient for a model
cost/independent-attempt acceptance report.

**Close when:** retain optional sanitized usage, provider identity and attempt
telemetry; separate cache hits, provider attempts and service-rendering latency.
Do not derive a cost claim from unavailable token/model/pricing information.

### AI-07 — Budget does not replenish during process lifetime

`service.py:NarrativeService` defaults to 200 configured generation attempts and
only increments `_requests_used`. Clearing/expiring cache entries does not reset
it. Once exhausted, otherwise valid requests keep returning budget_exhausted
until restart. This is an intentional safety cap, not a daily quota or global
Azure cost control.

**Close when:** define an operator-reviewed reset/replenishment policy and expose
non-secret exhausted/remaining status. Keep separate cloud budget controls;
verify sustained operation and multi-replica semantics.

### AI-08 — Recap frame choice is ignored

For the same recap packet and selected facts, analyst_frame=evidence and
analyst_frame=comparison produce byte-identical analyst output. The recap branch
never reads the field, although it is offered to the model.

**Close when:** implement a meaningful distinction or remove that choice for
recaps. Test the stated control rather than only Fan-versus-Analyst inequality.

### AI-09 — A valid custom fixture can defeat fallback

The fixture schema permits long team names. A validated fixture whose first team
name is `"Northstar " + "Quay " * 250` builds context, but narrative rendering
exceeds the output length limits. The initial fallback render occurs before the
provider try-block (`narrative.py:generate_narrative`); the service fallback calls
the same rendering path. The fixed golden fixture is not affected, but accepted
custom input can produce an exception rather than usable fallback.

**Close when:** bound source display strings or budget rendering safely, and
prove fallback remains renderable for every accepted fixture input.

### AI-10 — Environment setup needs an explicit handoff

README suggests copying .env.example to .env, but run.sh and the adapter do not
load that file. AI_ACCESS.md explicitly documents process environment variables,
so this is inconsistent onboarding, not a hidden implementation promise.

**Close when:** make the quick start explicitly export/load the variables or add
deliberate tested .env loading without leaking credentials. Verify a fresh-start
configuration test; never commit a populated .env.

## Selected reproducible probes

Run from the repository root with backend development requirements installed.
These reproduce findings; they do not change the golden data file.

```python
from backend.matchlens.evaluation import fixture_for_scenario
from backend.matchlens.narrative import generate_narrative
from backend.matchlens.story import build_recap_context
packet = build_recap_context(fixture_for_scenario('empty'))
print(generate_narrative(packet, allow_live=False)['analyst_explanation'])
# Currently includes unqualified 100%–0% possession despite empty event evidence.
```

For the high-scoring probe, copy load_fixture() deeply. Convert shot IDs e012,
e054, e061 and e068 to outcome='goal'; append one same-team/player goal per shot
at second+1 with related_event_id pointing to that shot; preserve chronological
order and call validate_fixture(). build_story() then reports:

```text
selected types:  goal, goal, goal, goal, goal, goal, goal
available types: goal, possession_swing, shot_surge
```

## Release decision

Keep the golden local demo usable, labelled and evidence-backed. Do not label
live AI acceptance complete until AI-01 is closed. Address AI-03/04/05 before
claiming robust arbitrary-fixture or real-time operation; measure AI-02/06 rather
than inferring model value/cost from green offline tests. Review the remaining
operational and low-priority items before a sustained public release.

## Remediation re-audit — October 26, 2026

The register above preserves the original findings against `c590301` for traceability.
The follow-up implementation supersedes its OPEN statuses as follows:

| IDs | Current status | Verification / required follow-up |
| --- | --- | --- |
| AI-01 | OPEN / BLOCKED | All-type and full-corpus live gates now reject partial or injected success. Real Foundry endpoint, deployment and credentials are still required to run them. |
| AI-02 | OPEN / HUMAN ACCEPTANCE | Direct baseline comparison and blinded audience review tooling added. Text differences do not establish usefulness; representative live selections need human ratings. |
| AI-03 | FIXED / offline verified | Unavailable possession omitted from recap percentage facts and prose; availability flag and UI qualification added. Legacy raw snapshot allocations remain for compatibility and must not be interpreted as observed when the flag is false. |
| AI-04 | FIXED / offline verified | Goal retention and pattern allowance are independent; bounded analyst output retains pattern coverage in high-scoring fixtures. |
| AI-05 | FIXED / offline verified | Parent deadline covers spawned transport startup, DNS and response work. Child terminated/reaped on expiry, with up to 100 ms bounded cleanup. Tested stalled native DNS and dripping responses; live network latency remains unmeasured. |
| AI-06 | FIXED / offline verified | Optional sanitized provider identity, tokens, request duration and attempt metadata retained. Unknown usage stays null; configured deployment is distinct from returned provider model. No inferred cost or pure-inference claim. |
| AI-07 | FIXED / offline verified | Atomic per-process fixed-window quota resets, default 200 attempts/hour. Health exposes remaining/reset status. Replicas have independent quotas; configure cloud spending controls separately. |
| AI-08 | FIXED / offline verified | Evidence and comparison recap frames now produce meaningful distinct analyst renderings. |
| AI-09 | FIXED / offline verified | Bounded, disambiguated display labels keep long accepted names renderable while canonical evidence remains unchanged. |
| AI-10 | FIXED / offline verified | Explicit tested dotenv startup loader, process-variable precedence, atomic validation and sanitized failures. |

Acceptance remains **not signed off as fully working live AI**. Offline regressions
and a working fallback do not close AI-01 or AI-02. Run
`scripts/check_ai_readiness.py`, then `scripts/evaluate_live_ai.py --live
--require-foundry --output live-report.json --review-output blinded-review.jsonl`
in the configured backend environment. Keep report mappings from reviewers,
collect ratings, and review latency/fallback/usage before release approval.
