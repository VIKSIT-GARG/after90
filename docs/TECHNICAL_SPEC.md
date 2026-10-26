# MVP technical specification

This is the implemented contract for the four-person work plan. Coordinate schema or API changes with both the backend and frontend owners.

## Core design

The browser owns a simulated minute and requests a snapshot for that minute. The Python API reads a versioned, synthetic fixture and derives all facts from events at or before that minute. Insight rules are deterministic. AI receives a compact object of verified facts and writes wording only. The UI displays canonical evidence from the API beside the wording.

Implemented stack: React + TypeScript frontend; FastAPI backend; JSON fixture; pytest backend checks; Vite build and TypeScript check. A multi-stage Docker image serves the React build and API together. Azure Container Apps is the documented deployment target, pending account access and a cost decision.

## Data contract (v1)

All IDs are synthetic and stable. Use integer match minutes 0-90; an optional `second` preserves ordering. `team_id` is one of the two fixture teams. Player names are fictional.

```json
{
  "id": "e042",
  "minute": 31,
  "second": 12,
  "type": "shot",
  "team_id": "blue",
  "player_id": "blue_09",
  "outcome": "saved",
  "possession_team_id": "blue"
}
```

Allowed `type` values for MVP: `pass`, `shot`, `tackle`, `possession_change`, `goal`. A goal is a distinct event linked to an earlier same-team shot through `related_event_id`. The linked shot has `outcome: "goal"`; the goal event changes the score but never adds a second shot. The fixture loader validates this convention.

### Statistics

- **Score:** count validated goal events per team.
- **Shots:** count shot events per team; a linked goal event does not add another shot.
- **Passes:** count pass events per team; pass success may be shown only if outcomes exist consistently.
- **Possession:** derive time share from possession-change timestamps; make the initial possessing team explicit. The two shares must sum to 100% after rounding. If event timing is too sparse for a credible percentage, show possession changes or intervals instead of a fabricated percentage.
- **Recent window:** use events with `minute > current_minute - 10` and `minute <= current_minute`; label the 10-minute window exactly.

## Insight rules (minimum three)

| Type | Trigger | Canonical evidence |
|---|---|---|
| Goal | A new validated goal event appears | Goal event ID, scorer/team, minute, score before and after |
| Shot surge | In a 10-minute window one team has at least 3 shots and at least 2 more than the other | Window bounds, each team's shot counts, shot event IDs |
| Possession swing | A team gains at least 30 possession percentage points between adjacent complete 10-minute windows, with a timed possession change in each window | Both window shares, change in points, possession event IDs |

Use one stable insight ID per triggering moment/window. The snapshot returns insight history to date, so polling does not create duplicate IDs. Early shot-surge windows start at minute 0 when fewer than ten minutes have elapsed.

## API contract

All four routes below are implemented. The explanation and recap endpoints return canonical facts with either screened Foundry wording or a deterministic template.

| Method/path | Purpose | Important response fields |
|---|---|---|
| `GET /api/health` | Public health check | `status`, `fixture_version` |
| `GET /api/matches/demo?minute=31` | Snapshot at minute 0-90 | `synthetic: true`, `minute`, teams, score, stats, `recent_events`, insight summaries |
| `GET /api/matches/demo/insights/{id}?mode=fan` | One explained insight | `insight_id`, `mode`, `text`, `evidence`, `source` (`foundry` or `template`) |
| `GET /api/matches/demo/recap?mode=fan` | Full-time recap | final score/stats, selected moment IDs, recap text, source |

Reject invalid minutes and modes with a clear 4xx response. The browser should not call the model for every clock tick: request explanation only when a new insight appears or a card is opened, then cache by fixture version, insight ID, and mode. Cache recap by fixture version and mode.

### Example snapshot shape

```json
{
  "match_id": "demo",
  "fixture_version": "v1",
  "synthetic": true,
  "minute": 31,
  "teams": [{"id": "blue", "name": "Harbor Blue"}, {"id": "red", "name": "Valley Red"}],
  "score": {"blue": 1, "red": 0},
  "stats": {"shots": {"blue": 4, "red": 1}, "passes": {"blue": 88, "red": 72}, "possession_percent": {"blue": 54, "red": 46}},
  "recent_events": [],
  "insights": [{"id": "surge-31-blue", "type": "shot_surge", "minute": 31, "evidence_event_ids": ["e039", "e040", "e041", "e042"]}]
}
```

The example values above are illustrative. The checked-in [minute-29 snapshot](samples/snapshot-minute-29.json) is generated from the actual fixture and is a regression example for UI integration.

## Explanation contract

Input to the explanation adapter is `{insight_type, minute, mode, verified_facts, evidence_event_ids}`. Output is `{text, source}`. The API adds the canonical `evidence` object; the model cannot edit it.

- Fan: one short sentence, everyday language; avoid unsupported causal claims.
- Analyst: one or two sentences, explicit comparison/window where the evidence supports it.
- Give the model no raw unvalidated feed and no instruction to infer unseen tactics or emotions.
- Check generated text before display. The current conservative validator rejects numeric claims, unsupported names or event references, causal/comparative claims, and text about a different insight metric. Verified numbers remain in canonical evidence and deterministic templates. On failure or timeout, use a template.
- If there are too few observations, say the evidence is limited. Avoid “momentum” as a fact unless the rule defines it operationally.
- Recap uses final facts and selected insight evidence only; no invented match narrative.

## Verification scenarios

1. At minute 0, the snapshot is valid and has no future events.
2. At every minute, score, passes, shots, and possession reflect only events at or before that minute.
3. A goal changes the score once; its linked shot changes the shot count once.
4. Resetting and replaying yields identical insight IDs and facts.
5. Switching modes changes wording while leaving score, evidence, and insight IDs unchanged.
6. A model failure returns an explicitly sourced template without blocking the replay.
7. A fabricated numeric/player claim from a stubbed model is rejected.
8. At full time, recap facts match the final snapshot.
9. Mobile and desktop UIs keep the synthetic label and evidence readable.

## Microsoft integration note

The backend has an optional adapter for the [Foundry Responses API](https://learn.microsoft.com/azure/foundry/openai/how-to/responses?tabs=rest), configured with `FOUNDRY_RESPONSES_URL`, `FOUNDRY_MODEL`, and `FOUNDRY_API_KEY`. The adapter is tested with an injected HTTP response but still needs a real deployment test. The container is prepared for [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/get-started-existing-container-image); no Azure service is claimed as live until deployed and checked.

## AI v1.0 staged service contract (October 24)

See [AI_CONTRACT.md](AI_CONTRACT.md) and [AI_DELIVERY.md](AI_DELIVERY.md).
The Wave 1/2 modules introduce canonical time-bounded context packets, typed fact
references, bounded narrative selection, paired server-rendered wording and a
ranked story ledger. They do not yet replace the legacy HTTP explanation/recap
endpoints. Phase 7 will integrate them with versioned caches and request recovery;
Phase 8 will connect the richer UI and overlay. This additive boundary preserves
the existing replay and is explicitly tested.

The model selects approved facts and framing. Exact scores, counts, player/team
attribution and outcome significance are rendered from verified server facts.
Arbitrary model prose is rejected rather than being treated as proven by regex or
JSON-schema compliance. Foundry selection, controlled rendering, injected tests,
and deterministic fallback must be distinguishable in reported provenance.
