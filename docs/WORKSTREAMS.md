# Four-person work plan

The percentages are planning estimates, not timesheets. **Billi has the heaviest workload (40%)** and owns the technical critical path. Each person has a distinct deliverable and an explicit handoff to the next person. Team members can pair on a blocked task without changing the owner.

| Person | Share | Primary ownership | First handoff |
|---|---:|---|---|
| **Billi** | **40%** | Synthetic data, backend, statistics, insight triggers, API, technical integration | Schema and sample snapshot to Ayesha/Maryam by Oct 18 |
| Ayesha | 22% | Product UX, React dashboard, controls, evidence view, responsive UI | Clickable shell using sample snapshot by Oct 19 |
| Maryam | 20% | AI wording, Foundry adapter, grounding checks, recap | Explanation interface and example outputs by Oct 19 |
| Zoya | 18% | Test plan, deployment, docs, demo/pitch/submission | Official rules/access report and smoke checklist by Oct 18 |

## Billi: data and application backbone (40%)

**Oct 17-19**

- Define shared event, snapshot, insight, and recap schemas with Ayesha and Maryam.
- Build a fixed-seed generator or author a golden synthetic fixture with plausible event order and stable IDs. Include passes, shots, tackles, possession changes, and at least one goal.
- Validate fixture chronology, team/player references, possession transitions, and score events.
- Implement pure functions to derive score, shot/pass counts, possession share, and rolling windows from events.
- Implement at least three deterministic insight rules: goal, shots surge, and possession/momentum swing.
- Give the team sample API JSON and golden expected stats.

**Oct 20-25**

- Expose snapshot, insight, and recap fact endpoints; support minute 0 through full time without server session state.
- Integrate Mary's explanation service behind the API and connect the frontend to the real endpoints.
- Add backend tests for replay, counts, insight evidence, invalid minutes, and missing-model fallback.
- Own technical triage and final integration; help Zoya deploy the backend and fix any production issues.

**Acceptance:** the same minute always returns the same facts; score/statistics match the fixture; each insight has verifiable evidence; the whole demo works if Foundry is temporarily unavailable.

## Ayesha: experience and frontend (22%)

**Oct 17-21**

- Sketch a one-screen layout: synthetic label, teams/score/clock, playback controls, event feed, stats, insights, and viewer-mode toggle.
- Build the React + TypeScript shell against Billi's sample JSON, then connect real API responses.
- Implement play/pause/reset/speed/jump-to-full-time; prevent duplicate calls when switching modes.
- Make score/insight states understandable without color alone.

**Oct 22-25**

- Add evidence details and recap view; keep fact badges identical across Fan and Analyst modes.
- Test common mobile and desktop widths, keyboard controls, loading/error states, and empty insight state.
- Polish the guided demo path and help Zoya capture the video.

**Acceptance:** a new viewer can start the replay, understand a key moment, switch modes, inspect evidence, and reach recap without guidance.

## Maryam: explanation and recap intelligence (20%)

**Oct 17-19**

- Define two voice guides: Fan = concise and plain; Analyst = precise, with window and comparison.
- Test Microsoft Foundry access with Zoya. Record model/deployment name, latency, cost assumption, and how credentials will be supplied privately.
- Define a structured explanation request/response and write examples based only on verified evidence.

**Oct 20-24**

- Implement Foundry-backed explanation adapter and deterministic template fallback for each insight type.
- Add output checks for unsupported numbers, players, or event references. When uncertain, return the fallback or say evidence is limited.
- Produce full-time recap from final score, verified statistics, and selected evidence-backed moments.
- Provide tests/examples for Fan and Analyst consistency, model failure, and weak evidence.

**Acceptance:** AI never calculates canonical statistics; both modes describe the same facts; no ungrounded claim appears in the UI; fallback is available and accurately described.

## Zoya: quality, delivery, and submission (18%)

**Oct 17-21**

- Verify official deadline, category, eligibility, repo/demo/video requirements, and whether public links need sign-in.
- Confirm Azure account, Foundry entitlement, permitted spend, and deployment access with Maryam/Billi.
- Turn MVP acceptance into a smoke checklist and test fixture edge cases with Billi.
- Create the public GitHub repo, issue board, contribution/secret setup, and initial deployment pipeline once accounts are ready.

**Oct 22-27**

- Run end-to-end checks at key milestones and log reproducible defects with minute/event IDs.
- Deploy the frontend/API, test the public demo in a private browser session, and document setup and limitations.
- Own the English pitch, under-two-minute demo video, public links, final submission checklist, and early submission.
- Recheck that all claims about Microsoft services and AI behavior match the actual build.

**Acceptance:** judges can open the public repo and demo, follow clear instructions, watch a real working flow in the video, and see an accurate technology statement.

## Handoff sequence

1. **Billi → Ayesha/Maryam, Oct 18:** shared schema, sample snapshot, fixture event IDs, insight evidence format.
2. **Maryam → Billi, Oct 19:** explanation/recap interface plus example Fan/Analyst responses and fallback behavior.
3. **Ayesha → Billi, Oct 20:** UI shell that renders the sample response and lists integration mismatches.
4. **Billi/Ayesha/Maryam → Zoya, Oct 23:** complete vertical slice and the exact demo path for public smoke testing.
5. **Zoya → team, Oct 25:** release candidate defects and deployment status; team fixes only release blockers.

## Daily 15-minute check-in

Each person reports one completed item, next item, and a blocker. Billi announces contract changes immediately. Zoya records decisions and keeps the board aligned with these files. Pair for one hour on a blocker before adding optional features.
