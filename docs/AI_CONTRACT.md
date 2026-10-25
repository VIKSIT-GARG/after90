# After90 AI contracts: version 1.0

This is the shared contract for the AI delivery plan's Waves 1 and 2. The older
five-phase plan describes the original MVP and is a separate sequence. The
snapshot/explanation/recap endpoints retain their core compatible fields and now
include the integrated rich service contract documented in API_V2.md.

The source models live in `backend/matchlens/ai_schemas.py`. Matching consumer
types live in `frontend/src/ai-contracts.ts`. Synthetic match data remains visible
in the UI. Canonical facts are calculated by the backend, never by the model.

## Context packet

`ContextPacket` has these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Literal `1.0` |
| `match_id`, `fixture_version` | Identity of the synthetic source |
| `insight_id`, `insight_type` | Stable moment ID and `goal`, `shot_surge`, `possession_swing`, `recap`, or `limited_evidence` |
| `minute` | Minute at which the insight became available |
| `as_of_minute` | Replay cutoff; cannot precede `minute` |
| `team_id` | Focal team or null for a whole-match packet |
| `teams` | Exactly two fixture team IDs mapped to fictional names |
| `facts` | Typed, uniquely identified computed facts |
| `evidence_event_ids` | Unique IDs selected from source events at/before the replay cutoff |
| `supported_interpretations` | Nonempty list of server-established interpretation codes |
| `limitations` | Canonical limitations; no claim of tracking/tactical evidence without data |

A `Fact` contains `id`, `metric`, `value`, and optional `team_id`, `player_id`,
`unit`, and `window`. A window is `{start, end}`, both inclusive integer minutes.
Its end cannot exceed `as_of_minute`. JSON numeric values must be finite. Top-level
values are strict numbers, strings, arrays, or objects. Nested arrays/objects may
include JSON booleans and null. Fact IDs and referenced teams are validated.
Player/event attribution and source-event chronology are validated by the context
builder using the fixture; a schema alone cannot establish those truths.

A full-time recap packet requires `minute = as_of_minute = 90`. A limited-evidence
packet should include a factual availability/count fact, even when no events were
supplied, so selection can remain evidence-backed.

## Supported interpretations

The codes are fixed strings:

- `GOAL_OPENS_SCORING`
- `GOAL_EQUALIZES`
- `GOAL_TAKES_LEAD`
- `GOAL_EXTENDS_LEAD`
- `GOAL_REDUCES_DEFICIT`
- `GOAL_RECORDED`
- `SHOT_SURGE`
- `POSSESSION_INCREASE`
- `LIMITED_EVIDENCE`
- `MATCH_RECAP`

The context/story builder decides which codes the facts support. A model cannot
create a new interpretation, mutate a score, or upgrade shot volume to chance
quality, pressing, tactical dominance, or expected goals.

## Model-authored selection versus rendered wording

`NarrativeSelection` is the only model-authored contract:

```json
{
  "selected_fact_ids": ["score_before", "score_after"],
  "interpretation_code": "GOAL_TAKES_LEAD",
  "fan_frame": "contextual",
  "analyst_frame": "evidence",
  "limitations": []
}
```

All fields are required, unknown fields are forbidden, and the schema has
`additionalProperties: false`. `fan_frame` is `concise` or `contextual`;
`analyst_frame` is `evidence` or `comparison`. The selection schema can be narrowed
at runtime to the current packet's fact IDs and interpretation codes for strict
Foundry structured outputs.

After parsing, `validate_against(packet)` checks that selected facts are unique,
nonempty and belong to this packet; the interpretation is supported; and selected
limitations are a unique subset of canonical limitations. The renderer must also
require the complete fact set needed by that interpretation. Reference existence
alone does not establish that an interpretation follows from the chosen facts.

`NarrativeOutput` is **server-rendered**, with `headline`, `selected_fact_ids`,
`interpretation_code`, `fan_explanation`, `analyst_explanation`, and `limitations`.
The two modes describe the same facts. Critical numbers and team attribution are
rendered from canonical facts using approved wording frames. Arbitrary model
prose must not be relabelled as this type merely because it parses as JSON.
The service retains canonical limitations even when a model selects a subset.

This bounded approach deliberately gives the model editorial selection and
framing rather than unrestricted factual writing. A later free-prose extension
would require semantic evaluation and must not claim schema checks eliminate
hallucinations.

## Provenance

`GenerationMetadata` requires:

- `source`: `foundry` or `template`.
- `fallback_reason`: null for accepted real Foundry output; a nonempty reason for
  template/fallback output.
- `model_version`, `prompt_version`: nonempty identifiers used for reproducibility
  and versioned caches.
- `latency_ms`: finite, nonnegative measured latency.

An injected test client is not live Foundry evidence. Services record injected
selection separately and never use it to assert a successful cloud connection.
No credentials, authorization headers, or provider exception bodies belong in
public metadata.

## Studio overlay

`Overlay` provides `insight_id`, `match_minute`, `headline`, `stat_line`,
`display_duration_ms` (1,000-30,000), `priority` (`low`, `medium`, `high`),
`evidence_event_ids`, `source`, and `synthetic: true`. The server renders the stat
line; the later UI/API integration phase will display the overlay and validate
its synchronization. This contract does not claim a live video integration.

## Checks and handoffs

Run `python -m pytest tests/test_ai_schemas.py` and `npm run build --prefix frontend`.

- Billi/context builder: canonical fact attribution, replay cutoffs, supported interpretations.
- Maryam/generation: bounded selection, complete evidence requirements, safe wording, provenance.
- Ayesha/frontend: consumer types and later personalized presentation/overlay integration.
- Zoya/evaluation: temporal, contradiction, attribution, fallback and source-label checks.

Live Foundry access, Azure budget/permissions, team registration and the public
release are separately verified gates, not properties that these schemas can
prove.

## Complete service envelope

`NarrativeResult` combines the server-rendered `NarrativeOutput` fields with
`source`, `selection_source` (`foundry`, `injected`, `deterministic`),
`selection_accepted`, `selection` (`NarrativeSelection`), `metadata`
(`GenerationMetadata`), `validation` (`ValidationMetadata`), and `evidence`
(`ContextPacket`). `ValidationMetadata` contains `passed`, `reason`, and
`transport` (`foundry`, `injected`, `offline`). `passed` describes model-selection
acceptance, not whether fallback text is valid or a live quality evaluation passed.

The envelope rejects conflicting source labels, acceptance/validation disagreement,
fallback-reason disagreement, changed fact references/interpretations, and dropped
canonical limitations. `source: foundry` requires an accepted Foundry selection
and Foundry transport. Accepted injected clients remain `source: template` with
`selection_source: injected` and `fallback_reason: injected_client`. Offline output
cannot claim accepted model selection. A rejected selection uses deterministic
fallback and retains the applicable failure reason.

These structural checks do not prove live access or semantically validate arbitrary
prose: only the server renderer constructs the wording, and live integration and
quality evaluation remain separately evidenced gates.
