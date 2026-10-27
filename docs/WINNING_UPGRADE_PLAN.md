# After90: priorities for a stronger hackathon entry

Focus category: explainable synthetic match intelligence, with meaningful use of
Microsoft Foundry. A polished interface supports the product; acceptance depends
on actual model operation and usefulness, rather than the number of services.

## Delivery order

| Wave | Work | Parallel or prerequisite | Exit evidence |
| --- | --- | --- | --- |
| 1: connection and interaction | Foundry resource/model setup, private connection wizard, Ask the match UI/API, shared provider budget, topic/evidence tests | Setup and UI/API can run in parallel against an agreed contract | Implemented; offline/API/browser checks, no live-provider claim |
| 2: actual Azure acceptance | Choose available model/version/region/SKU, apply reviewed deployment, configure privately, run narrative plus Copilot live evaluation | Requires authorized subscription, quota and reviewed spending settings; after wave1 | Accepted real requests for every narrative type and supported Copilot topic, measured usage/latency, human baseline review |
| 3: deeper personalization | Player lens built from the fixture roster and per-player recorded events; optional favorite-team ordering | Deterministic aggregation can be built beside wave2; model personalization acceptance needs wave2 | Correct player stats/evidence at earlier cutoffs; distinct useful audience experiences |
| 4: global and spoken experience | A second language with bilingual fact checks, optional Azure Speech narration/voice questions, accessible transcript and text controls | Requires working core AI plus approved Speech resource and human language review | Measured end-to-end behavior, correct names/numbers, explicit voice action, secure server credentials |
| 5: release and presentation | Container Apps deployment, public smoke checks, proof of real AI, final under-two-minute demo and submission links | Hosting plan can be prepared in parallel; final proof follows waves2 and completed chosen features | Verified public URL, clean browser tests, actual model output and complete submission |

The current runtime is a bounded planner/router plus deterministic computation
and validation. Do not claim a multi-agent runtime or enter a multi-agent award
on that basis. Add specialized runtime agents only when a distinct task, shared
state, useful handoff and failure recovery can be demonstrated and evaluated.

## Evidence to collect before calling the AI complete

- Run `scripts/evaluate_live_ai.py --live --require-foundry`: all 13 narrative and
  recap contexts must show accepted real-provider provenance.
- Run `scripts/evaluate_copilot.py --live --require-foundry`: all 6 supported
  question cases, including a paraphrase, must pass with real-provider evidence;
  the future-question guard must remain local and replay-safe.
- Record optional provider model/usage/request time; do not equate network request
  duration with pure model inference or infer cost from missing usage.
- Complete blinded human comparison against the deterministic baseline. Text
  differences and injected tests alone do not prove viewer value.

## Reference video

Reference supplied by the user: https://www.youtube.com/watch?v=kxUgW9XjT_M,
identified through YouTube metadata as “Ruling : Microsoft's Inside the Game
(Developer Hackathon)” (117 seconds). Full transcript, frames and playback could
not be retrieved in this environment. No specific feature or design comparison
is asserted from unviewed content. A playable clip or accessible transcript is
needed before using concrete reference cues. No video assets are copied into the
project.

## Microsoft services and their purpose

- Foundry: interpret supported question paraphrases and select approved narrative
  facts/framing. It cannot overwrite match statistics.
- Container Apps: serve the existing API and frontend together.
- Speech (planned): make the same verified intelligence available through an
  explicit spoken experience; text/evidence remain available.

An external search index is not required for the 225-event structured fixture.
If retrieval is introduced later, it must use synthetic authorized data and
preserve replay cutoffs. Do not add cloud services solely for a technology list.
