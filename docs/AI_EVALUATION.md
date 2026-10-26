# After90 AI evaluation

This is the delivery-plan Phase 3 corpus and Wave 2 regression harness. It tests
synthetic match facts and the bounded narrative-selection boundary. It does not
claim that a live model was contacted or that generated language was rated by a
human.

## Run

From the repository root:

```sh
python scripts/evaluate_ai.py
python scripts/evaluate_ai.py --category snapshot
python -m pytest tests/test_ai_evaluation.py
```

The CLI prints JSON to standard output and exits nonzero when a check fails.
Redirect to a local file when retaining a report. No network or cloud credentials
are required. Generation cases supply an injected client, so an accepted injected
selection is explicitly `selection_source: injected`, not evidence of live
Foundry use.

## Coverage

`tests/fixtures/ai_cases.json` contains 60 individually named cases:

| Group | Cases | Checks |
| --- | ---: | --- |
| Snapshot ground truth | 18 | Golden score/counts, exclusive recent window, single shot/goal accounting, deterministic reset, no future leakage, draws, goalless and empty fixtures, minute 90 |
| Evidence/context | 14 | Opener, equalizer, comeback lead, extended lead, reduced deficit, late goal, supported interpretation, linked evidence, limitations and invalid lookups |
| Generation boundary | 22 | Valid bounded selection, paired modes, unknown/duplicate/empty facts, wrong interpretation, invalid frames, invented limitations, refusal, malformed output, timeout, network failure and contradictory free prose |
| Story/recap | 6 | Empty-evidence limitation, golden/draw/comeback final facts, valid event references and story as-of cutoff |

The golden fixture is read-only. Additional fictional fixtures are constructed in
memory and run through the production fixture validator before any check. The
corpus contains independent scenarios rather than 60 copies of the same prompt.

## What the report proves

- A pass verifies the exact assertion for the recorded case and current code.
- `deterministic` provenance means engine/context/story logic was exercised.
- `injected_client` provenance means production generation was exercised with a
  controlled response or failure. The generation service must not label this as
  live Foundry.
- `duration_ms` is local harness duration, not network or model latency.
- `live_model_metrics.status` remains `not_measured`; token usage, live factual
  error rate and latency remain null.
- `human_usefulness.status` remains `pending_human_review`.

## Release evaluation still required

After access is configured, retain the model deployment and prompt versions and
run the actual Foundry transport against the same contexts. Record attempts,
accepted selections, fallback reasons, observed latency (including p50/p95 when
sample size permits), and token usage if returned. Divide failures by actual
attempts; do not exclude refusals/timeouts from operational reporting.

Have a reviewer assess usefulness, factual relevance, Fan/Analyst distinction,
readability, and recap coherence. Review the rendered desktop/mobile UI and
screen-reader/focus behaviour separately: offline assertions cannot establish
visual accessibility or real user value. Keep reports of injected checks, live
model evaluation, and human review separate.

## Uncached live coverage and paired baseline measurement

```sh
python scripts/evaluate_live_ai.py
python scripts/evaluate_live_ai.py --live --require-foundry --output /tmp/after90-ai-report.json --review-output /tmp/after90-review.jsonl
python -m pytest tests/test_live_ai_evaluation.py tests/test_ai_integration.py
```

The default is strictly offline even when credentials exist. `--live` explicitly
permits provider calls. Each of the 12 golden insights and the recap is evaluated
once directly, bypassing the service cache; each result contains both modes.
`--require-foundry` requires `--live`, all contexts accepted by the actual
provider, and coverage of goal, shot surge, possession swing and recap. Missing
configuration, fallback in any context, and injected clients cannot close this
gate. The HTTP evaluator separately requires both observed modes of every type
but reports response counts which can include cached results.

Each context also renders the deterministic fallback from the identical packet.
The report compares selected facts, bounded selection, text similarity and length
changes. These are editing statistics, **not evidence that AI is better**. The
JSONL review export contains 26 stable blinded A/B pairs, canonical evidence and
pending relevance, clarity and usefulness fields. Keep the full report, which
contains the A/B mapping, away from reviewers. Empty/sparse fixtures remain usable
without pretending assumption-derived possession is measured.

To import human observations, supply `--ratings /path/ratings.json`: a JSON list
of objects with `review_id`, `A`, `B`, and `preferred`. Each side must contain
integer `relevance`, `clarity`, and `usefulness` ratings from 1 through 5;
`preferred` is `A`, `B`, or `tie`. Unknown and duplicate IDs are rejected. Remove
mode, evidence, text and pending wrapper fields from completed export rows when
creating this ratings list. Ratings are reported as supplied, not independently
verified; no numerical score automatically establishes factual safety or approval.

Provider request telemetry includes model/response/request identifiers and token
usage when returned. Missing usage remains null, never an invented zero. Usage
sums include only observed actual-provider attempts, with observed sample counts.
Provider request wall time includes transport and provider processing; pure model
inference time is unavailable. Service time includes validation and rendering;
direct total time adds evaluator overhead. No pricing or cost is inferred.

Live provider acceptance and human usefulness remain **unverified until an
authorized credentialed run and actual human review are retained**. Unit tests
simulate transport only to verify gate behavior and cannot establish live proof.
