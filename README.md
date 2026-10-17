# MatchLens (working title)

An AI-assisted match companion for a **fictional** football match. It replays synthetic events, calculates checkable statistics, explains important moments for casual fans or analysts, and produces a final recap.

**Current status:** Phases 1 and 2 are built. The Python API replays a checked-in synthetic fixture and serves deterministic snapshots. The React frontend is a responsive shell; interactive replay, AI explanations, and recap are scheduled for phases 3-5. The name and final hosting choices are provisional.

## Run locally

Prerequisites: Python 3.11 or newer, Node.js supported by the current Vite release, npm, and Make.

```sh
make setup
make test
make build
```

Start the two development servers in separate terminals:

```sh
make backend
make frontend
```

Open `http://localhost:5173` for the frontend shell or `http://localhost:8000/docs` for API documentation. The snapshot endpoint is `GET http://localhost:8000/api/matches/demo?minute=29`; valid minutes are 0-90. The frontend does not consume this endpoint until Phase 3.

The backend fixture is `data/demo_match.json`: 225 fictional events, including three linked goals. Its final score is Northstar Quay 2, Copper Vale 1. All displayed data must remain labeled **Synthetic match data**.

## What the demo must show

1. Start a 90-minute simulated match and watch events arrive.
2. See the score, shots, passes, and possession update from those events.
3. Open an insight and see both its explanation and the supporting numbers/events.
4. Switch between **Fan** and **Analyst** modes for the same insight.
5. Jump to full time and read a recap.
6. See a clear **Synthetic match data** label throughout the experience.

## Planning files

- [Project plan](docs/PROJECT_PLAN.md): MVP, schedule, milestones, risks, and decisions.
- [Five phases](docs/PHASES.md): delivery sequence and current build boundary.
- [Workstreams](docs/WORKSTREAMS.md): four-person ownership and handoffs; Billi has the largest workload.
- [Technical spec](docs/TECHNICAL_SPEC.md): architecture, data rules, API contract, and acceptance tests.
- [Actual minute-29 snapshot](docs/samples/snapshot-minute-29.json): fixture-derived API example for Phase 3 integration.
- [Submission checklist](docs/SUBMISSION_CHECKLIST.md): launch checks, pitch, and demo script.
- [AGENTS.md](AGENTS.md): instructions for anyone or any coding agent working in this repo.

## First team meeting: October 17

- Confirm the final project name and target category.
- Confirm the organizer's actual submission date/time and time zone. October 27 is only the team's proposed target in the supplied brief.
- Check Microsoft Foundry access, Azure subscription/credits, and who may deploy.
- Agree that the first release has one fixed, replayable synthetic fixture and two viewer modes.
- Create the public GitHub repository and protect any credentials from commits.

Source: the team's seven-page hackathon brief, supplied separately as `hackathon microsoft-1.pdf`.
