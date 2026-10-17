# Five-phase delivery plan

This sequence turns the hackathon brief into one working demo. Dates are team targets from the brief; Zoya must verify the organizer's actual cutoff. **Phases 1 and 2 are built.** Later phases remain planned.

| Phase | Target | Owner and support | Deliverable | Exit gate |
|---|---|---|---|---|
| **1. Foundation and contracts** | Oct 17-18 | Billi leads; Ayesha, Maryam, Zoya review | Repository structure, backend/frontend bootstraps, shared event and API contract, local run instructions, synthetic-data rules | Both apps start locally; API health works; data contract and handoffs are documented |
| **2. Synthetic match engine** | Oct 18-20 | **Billi leads**; Zoya verifies | Seeded fictional fixture, loader/validation, event-derived score/stats, evidence-backed rule insights, stateless snapshot API, behavior tests | Minutes 0-90 return deterministic snapshots; goal/shot/pass/possession counts and insight evidence pass tests |
| **3. Interactive match experience** | Oct 20-22 | Ayesha leads; Billi integrates | Dashboard, clock, replay controls, event feed, stats, evidence cards, responsive design | A viewer can replay, pause, reset, jump, and inspect evidence in a browser |
| **4. AI explanations and recap** | Oct 22-24 | Maryam leads; Billi integrates | Foundry-backed explanations if access exists, grounded Fan/Analyst modes, fallback, full-time recap | Two modes retain identical facts; model failure and unsupported claims fall back safely; recap matches final stats |
| **5. Release and submission** | Oct 24-27 | Zoya leads; all support | QA, deployment, documentation, pitch, public repo/demo, under-two-minute video, submission | Public links work without team login; requirements and official deadline are checked; submission receipt saved |

## Implementation status (October 17)

- [x] Phase 1: shared Pydantic event contract, Python API and React bootstraps, local run commands, visible synthetic-data label, health endpoint.
- [x] Phase 2: validated 225-event golden fixture, event-derived score/stats, three evidence-backed insight rules, stateless minute snapshot endpoint, behavior and integration tests.
- [ ] Phase 3: interactive replay dashboard and evidence view.
- [ ] Phase 4: grounded Fan/Analyst explanations and full-time recap.
- [ ] Phase 5: release checks, public deployment, video, and submission.

## Current implementation boundary

Phase 2 exposes `GET /api/health` and `GET /api/matches/demo?minute=0..90`. Insight explanation and recap endpoints belong to Phase 4. The Phase 1 frontend is a compilable shell; replay UI belongs to Phase 3. This boundary keeps completion claims honest.

## Critical dependencies

1. Phase 1 schema precedes fixture, engine, and UI integration.
2. Phase 2 snapshot response precedes Phase 3 live dashboard integration.
3. Phase 2 verified evidence precedes Phase 4 generated wording.
4. Phase 5 uses the actual deployed build and services; it cannot be replaced by mockups.

## Scope control

At each gate, fix correctness and integration defects before adding options. Player focus and extra languages wait until all five phases work. Video detection, real feeds, and multiple cooperating AI agents stay outside this MVP.
