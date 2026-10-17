# Working instructions for contributors and coding agents

Read `README.md`, `docs/PROJECT_PLAN.md`, and `docs/TECHNICAL_SPEC.md` before implementing a feature. The supplied hackathon brief is the product source; these files turn it into an executable MVP plan. Update the plan when a team decision changes scope or ownership.

## Product rules

- Every match, team, player, and event in the demo is fictional. Label all match views and submission materials **Synthetic match data**. Never imply access to official Premier League feeds or marks.
- Treat event records as the source of truth. Calculate score and statistics in ordinary code, then pass verified facts to AI for wording.
- Every displayed insight must cite supporting event IDs or computed facts. If evidence is weak, say so; never invent a cause, player action, or number.
- Provide Fan and Analyst explanations for the same underlying insight. The difference is language and detail, not facts.
- Keep the demo deterministic: a given fixture and minute must return the same events, score, statistics, and insight triggers. AI text may be cached or use a documented fallback.
- Keep a functioning match replay without Foundry credentials. Label template-generated explanations honestly; do not claim AI was used when it was not.

## Scope and decision order

1. Must work: synthetic fixture, playback controls, event feed, score and statistics, evidence-backed insights, two modes, recap, public demo.
2. Add only after the complete vertical slice works: player focus or a second language.
3. Outside MVP: video detection, computer vision, player tracking, real feeds, live broadcast integration, user accounts, and an agent swarm.

## Architecture boundaries

- `frontend/`: React + TypeScript UI; presentation and playback controls. Never put secrets or model calls in browser code.
- `backend/`: Python API, fixture loading, statistics, rule-based insight detection, explanation service, and recap. The API contract is in `docs/TECHNICAL_SPEC.md`.
- `data/`: versioned synthetic match fixture(s) and any generation seed/configuration. Avoid copyrighted or real match play-by-play data.
- `docs/`: product decisions, setup, evidence of testing, deployment, and submission materials.
- `tests/`: behavior checks for fixture validity, statistics, API contracts, explanation evidence, and replay. Teams may keep language-specific tests beside their code.

The `frontend/`, `backend/`, `data/`, `docs/`, and `tests/` directories now exist. Phases 1–4 and the local Phase 5 package are built; see `docs/PHASES.md` for the remaining public release gates. Do not add an unrelated framework or cloud service without recording the reason in `docs/PROJECT_PLAN.md`.

## Ownership and collaboration

- **Billi (40%)** owns backend foundation, event generator/fixture, statistics, insight detection, API integration, and final technical integration. This is the largest workstream.
- **Ayesha (22%)** owns frontend UX and responsive match dashboard.
- **Maryam (20%)** owns AI explanation/recap design, Foundry integration if available, and wording safeguards.
- **Zoya (18%)** owns quality checks, deployment, documentation, and submission/demo production.

See `docs/WORKSTREAMS.md` for dated deliverables and handoffs. Owners may ask for help, but only the owner closes a task after its acceptance criteria pass. Avoid editing another person's active work area without coordinating first.

## Implementation contracts

- Agree on event and API types before parallel implementation. Change an API/schema through a small PR that updates both `docs/TECHNICAL_SPEC.md` and its consumers.
- Use a fixed random seed and stable event IDs for fixtures. Preserve a golden fixture for the demo.
- Use a stateless `minute` parameter for replay snapshots so the demo can reset and jump ahead reliably; the browser controls playback time.
- Keep Foundry behind a backend adapter. Credentials belong in local environment variables and hosting secrets, never Git or frontend bundles. Provide `.env.example` with names only.
- Set short model timeouts and use a deterministic template fallback. Show an explanation-source indicator in development and in submission claims.
- Reject or replace model output with unsupported numeric claims or event references. Return canonical evidence from code separately from prose.
- Use accessible labels, keyboard-operable controls, readable contrast, and responsive layout.

## Definition of done

A feature is done when it works from a clean checkout with documented setup, has a relevant behavior check, has no credential exposure, and is demonstrated in the UI/API. For insight or recap work, test a case with limited evidence. For UI work, check desktop and mobile widths. For deployment work, test the public URL in a private browser session.

Before merging: run the affected tests/build, inspect the diff, and update documentation if behavior or setup changed. Keep PRs focused and include a short test note. By October 25, merge only fixes needed for the demo and submission.
