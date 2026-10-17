# Five-phase delivery plan

This sequence turns the hackathon brief into one working demo. The phase dates are team targets. Microsoft's [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) set registration at October 20, 2026 noon Pacific and submission at October 27, 2026 11:59 p.m. Pacific. **Phases 1–4 and the local Phase 5 package are built.** Public release remains a team action.

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
- [x] Phase 3: interactive replay dashboard, event feed, evidence view, and responsive layout; desktop and mobile browser flows checked locally.
- [x] Phase 4: grounded Fan/Analyst explanations, optional Foundry adapter with deterministic fallback, and full-time recap. Live Foundry access remains unverified.
- [ ] Phase 5: local container, CI, smoke check, deployment runbook, and demo script are ready; public deployment, video hosting, registration, and submission remain open.

## Current implementation boundary

The API exposes health, minute snapshots, evidenced insight explanations, and full-time recap. The frontend uses all four routes. The built frontend and API run in one container. Without configured Foundry credentials, the API labels explanation and recap text as `template`; no live Foundry or Azure deployment is claimed.

## Critical dependencies

1. Phase 1 schema precedes fixture, engine, and UI integration.
2. Phase 2 snapshot response precedes Phase 3 live dashboard integration.
3. Phase 2 verified evidence precedes Phase 4 generated wording.
4. Phase 5 uses the actual deployed build and services; it cannot be replaced by mockups.

## Scope control

At each gate, fix correctness and integration defects before adding options. Player focus and extra languages wait until all five phases work. Video detection, real feeds, and multiple cooperating AI agents stay outside this MVP.
