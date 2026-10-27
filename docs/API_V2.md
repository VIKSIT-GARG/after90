# After90 integrated AI API (0.2)

The existing routes now use the bounded context/narrative/story pipeline. The
legacy regex-screened `explanations.py` helper is no longer called by public API
routes. It remains only for historical standalone compatibility tests.

All matches, events, teams and players are fictional. Outputs include
`synthetic: true`; the frontend keeps the **Synthetic match data** label visible.

## Routes and replay cutoffs

| Route | Query | Contract |
| --- | --- | --- |
| `/api/health` | none | Existing status/fixture/synthetic plus `ai` configuration presence; never claims live proof |
| `/api/matches/demo` | `minute=0..90` | Existing canonical snapshot |
| `/api/matches/demo/insights/{id}` | `mode=fan|analyst`, `as_of_minute=0..90` | Legacy fields plus paired narrative, metadata, overlay and limits |
| `/api/matches/demo/recap` | `mode=fan|analyst`, `as_of_minute=90` | Full-time narrative and canonical final statistics; 409 before full time |
| `/api/matches/demo/story` | `minute=0..90` | Deterministic selected/all story moments available at that cutoff |
| `/api/matches/demo/overlay` | `minute=0..90`, optional `insight_id` | `{as_of_minute, synthetic, overlay}`; null overlay before an insight exists |

For backward compatibility, omitted `as_of_minute` defaults to 90. Replay clients
must send their actual displayed minute. Unknown/future insight IDs return 404,
including when another client already cached that insight at full time. Invalid
query types/ranges/modes return 422. An explicit overlay ID uses the same cutoff
check. Without an ID, overlay selection uses highest significance, then latest
minute, among the available story moments.

A moment's narrative describes its original score/window, not later match state.
The paired cache is therefore keyed by the canonical moment, while the public
response's `as_of_minute` echoes the observation cutoff. The nested narrative
packet retains the moment's own available minute. This permits mode changes and
later inspection to share the same fact-backed narration without future leakage.

## Insight response

Legacy consumer fields are preserved: `insight_id`, `mode`, `text`, `source`, and
`evidence` with `event_ids` and the insight's existing score/window facts.
Additional fields:

- `headline`, `limitations`, `synthetic`, `as_of_minute`.
- `narrative`: the validated `NarrativeResult` envelope from AI_CONTRACT.md,
  containing both audience versions, context facts, selected references and
  explicit generation provenance.
- `metadata`: identical generation metadata for convenient badge/status use.
- `overlay`: server-rendered `Overlay` with time, headline, stat line, priority,
  suggested display duration, source and supporting event IDs.
- `cache_expires_in_seconds`: remaining server cache life at this response.

The model selects facts and approved frames. Factual wording is rendered by the
server. `source: foundry` therefore means **AI-selected narrative**, not arbitrary
model prose. Missing configuration, invalid output or provider failure returns a
labelled `template` source with a non-secret reason code. Injected tests never
establish live Foundry use. The UI should present readable source information,
not raw model deployment names or provider errors.

Recap responses retain `final_score`, `stats`, `moment_ids`, `mode`, `text`, and
`source`, adding the same rich metadata/narrative/overlay fields. Their top-level
`evidence` is the full-time context packet.

## Reliability and resource bounds

`NarrativeService` caches one paired result per insight/recap, so switching
Fan/Analyst does not generate a second provider request. Private cache identity
includes a hash of fixture content, provider configuration (including credential
rotation), and prompt version. No raw credentials or hashes are returned.

- Successful real Foundry selection TTL: 600 seconds.
- Template/provider-failure TTL: 15 seconds, allowing automatic recovery.
- Maximum cached entries: 128, with expiry/LRU eviction.
- Maximum in-flight cache keys: 16; bounded wait for an identical in-flight key: 5 seconds.
- Provider calls run outside the global cache bookkeeping lock.
- Default maximum concurrent configured-provider calls: 2.
- Default provider request budget: 200 attempts per process lifetime.

Use `AI_MAX_CONCURRENT_REQUESTS` (0 disables configured calls, capped at 16) and
`AI_MAX_REQUESTS_PER_PROCESS` (0 disables configured calls, capped at 10000) to
bound usage. These are local-process limits, not shared across replicas and not
a substitute for Azure quota/spend controls. A restart resets the process budget.
Unconfigured operation does not consume provider budget. Saturation, exhausted
budget and in-flight timeout produce a canonical template instead of blocking
replay. Invalid generator envelopes or mismatched evidence are replaced before
being cached. Returned cache values are isolated copies.

Client caches must respect expiry and allow template recovery; a retry must not
be served an indefinitely cached fallback. API cache/versioning tests cover
concurrency, expiry, source/configuration changes, future lookup, and invalid
provider results. Real Foundry quality, deployed-Azure and public/browser checks
remain separate release evidence.

## Verify

```sh
python -m pytest tests/test_api.py tests/test_ai_api.py
python scripts/evaluate_integrated.py
```

## Match Copilot

`POST /api/matches/demo/copilot` accepts an explicit question request:

```json
{"question":"Compare the shots","minute":29,"mode":"analyst"}
```

Question length is 1–600 characters after nonblank validation; minute is an
integer 0–90 and mode is `fan` or `analyst`. Extra fields are rejected. The response
contains `question`, `answer`, `as_of_minute`, `topic`, `source`, `metadata`,
`evidence_event_ids`, `facts` (`label`/`value` pairs), `limitations` and
`synthetic:true`. `metadata` uses the existing generation contract.

Topics are `score`, `shots`, `passes`, `possession`, `key_moments` or `unsupported`.
Foundry can select a topic for a supported paraphrase; ordinary code supplies
facts and final answer wording. Only an accepted real-provider routing request
uses `source:foundry`. Rules and injected selectors use `source:template`.
Configuration presence alone is not live proof. Narrative selection and question
routing share process request/concurrency limits.

Answers cover cumulative match-level totals or supported moments through the
requested minute. References cannot include future events. Unavailable measured
possession is qualified. Predictions, tactical causes, player analysis, foreign
subjects and arbitrary sub-windows are outside this endpoint's supported scope.
Evidence is capped at 200 references with an explicit omission note if necessary;
totals still include all matching recorded events through the cutoff.

The browser submits only on an explicit action, pauses playback for inspection,
and clears/aborts stale requests when replay context or mode changes. No
conversation history is retained. A cancelled browser request does not undo a
provider attempt already started; its transport remains bounded by the deadline.
