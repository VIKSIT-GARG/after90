# Integrated HTTP evaluation

The Phase 9 runner checks the actual FastAPI context → bounded narrative →
service/cache → HTTP response pipeline. It complements the 60-case offline corpus
and frontend/browser checks; it does not replace them.

## Commands

```sh
python scripts/evaluate_integrated.py
python -m pytest tests/test_ai_integration.py
python scripts/evaluate_integrated.py --url http://127.0.0.1:8000
python scripts/evaluate_integrated.py --url https://YOUR-APPLICATION.azurecontainerapps.io --live --require-foundry
```

The default runner uses `TestClient` and temporarily injects a service whose
narrative generation is explicitly `allow_live=False`. This holds even if the
machine has valid Foundry credentials. The previous application service is
restored after execution.

`--url` makes bounded, read-only HTTP requests to an application origin. Without
`--live`, it checks only health, deterministic snapshots and story routes; these
routes do not generate narratives. Generation routes are deliberately skipped
because the remote server might call its configured provider. `--live` explicitly
allows those requests; a resulting template fallback remains a fallback and is
not live Foundry evidence. Local `--live` allows the actual configured adapter.
`--require-foundry` requires `--live` and makes the command fail unless at least
one observed generation response reports accepted Foundry selection. Use both
flags for the live-service release gate; plain `--live` intentionally permits a
healthy fallback-only service to pass its functional checks. This additional
requirement does not independently attest a remote application's provenance.

Application URLs must be HTTPS, except local HTTP origins. Credentials, query
parameters, fragments and paths are rejected. The runner sends no model keys,
disables redirects, limits response size, and avoids printing raw service errors.
Exit status is zero for passing selected checks, one for failed checks, and two
when evaluation cannot start.

## What is checked

The full local run has eight checks:

1. Health and the synthetic-data flag.
2. Replay snapshots, possession totals and canonical goal availability.
3. Story cutoffs before kick-off and at full time.
4. Paired modes preserve the same facts and selected evidence.
5. Responses conform to the bounded narrative contract and retain limitations.
6. A cached future insight remains unavailable when seeking backwards.
7. Recap facts match the final snapshot; early recap requests are rejected.
8. Typed overlay provenance and timestamp do not exceed the replay cutoff.

The regression tests additionally prove the HTTP routes bypass the legacy
free-prose helper, reject injected contradictory prose, recover from a simulated
model failure without claiming injected output is live AI, share paired-mode
generation, and cannot accidentally call the provider in offline evaluation.
Cache-expiry and concurrency assertions are maintained in the Phase 7 service
suite; visual layouts and keyboard flows are maintained in the browser suite.

## Metrics and limits

- `api_latency_ms` measures recorded probe requests including application/HTTP
  overhead. It is not model inference latency.
- `generation_service_latency_ms` comes from response metadata and covers the
  adapter, validation and rendering. Cached Fan/Analyst responses can repeat the
  same generation duration.
- Nearest-rank p50/p95 values are accompanied by sample count and a small-sample
  flag. A tiny smoke run is not a performance benchmark.
- Source counts and fallback rates count observed responses, not independent
  provider attempts. Cache hits must not inflate claimed model success rates.
- `provider_inference_latency_ms` remains `not_measured`; no token usage or model
  quality result is fabricated.
- The template baseline comparison checks structural facts and mode differences.
  Human preference and AI improvement remain unmeasured.
- Remote Foundry provenance is application-reported, not independently attested.
- Human usefulness, browser accessibility and public Azure deployment remain
  separate acceptance fields. A passing local runner does not close those gates.

## Recorded local result

On October 25, 2026: **18 integration regression tests passed**, and the default
runner passed **8/8 HTTP checks** with deterministic offline templates. No live
Foundry request or public deployment was established by this run. Re-run after
API or service changes and retain the full JSON report for the actual release.
