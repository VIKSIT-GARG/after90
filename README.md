# After90

After90 is a replayable companion for a **fictional football match**. It derives scores, statistics, and insight evidence from 225 synthetic events, then explains moments in Fan or Analyst mode. The final recap uses the same verified match facts. Every match view is labeled **Synthetic match data**.

**Build status:** The original five-phase MVP has its replay baseline and local release package implemented. The new AI delivery plan has separate phase numbers and service-verification gates. The dashboard and container pass local checks. Public Azure deployment, a hosted video, team registration, and the final hackathon submission still require the team's accounts and decisions. Microsoft Foundry is an optional server-side integration; the current local demo uses clearly labeled deterministic templates because no Foundry credentials are configured.

![MatchLens dashboard showing a fictional goal insight and its supporting events](docs/assets/dashboard.png)

## Run locally

Install Python 3.11+, Node.js 22+, npm, and Make. From the repository root:

```sh
make setup
make test
make build
```

Run the API and Vite development server in separate terminals:

```sh
make backend
make frontend
```

Open `http://localhost:5173`. Vite proxies `/api` to the API on port 8000. The dashboard needs both development servers. API documentation is at `http://localhost:8000/docs`.

For a single process that serves the built page and API, use Docker:

```sh
docker build -t matchlens:local .
docker run --rm -p 127.0.0.1:8000:8000 matchlens:local
```

Open `http://127.0.0.1:8000` and run `python3 scripts/smoke_deployment.py http://127.0.0.1:8000` in another terminal.

## How it works

1. `data/demo_match.json` stores a versioned, fictional fixture. Its final score is Northstar Quay 2, Copper Vale 1.
2. `backend/matchlens/engine.py` derives snapshots for minutes 0–90. Goals, shots, passes, possession, and insight IDs come from events rather than generated prose.
3. `backend/matchlens/api.py` exposes snapshot, explanation, recap, and health routes. `backend/matchlens/explanations.py` passes verified facts to a configurable Foundry Responses endpoint when all three `FOUNDRY_*` variables are set. Generated wording is screened; failed or unsupported wording falls back to a deterministic template. API responses identify `source` as `foundry` or `template`.
4. `frontend/` displays playback controls, event feed, statistics, evidence cards, mode switching, and a full-time recap. It caches snapshots and wording by fixture version and mode.

The browser never receives a model key. Copy `.env.example` to a local `.env` only if configuring Foundry, and supply runtime secrets through the hosting environment. No real football feed, official league mark, or live player data is used. The optional Foundry path has unit tests with a stubbed endpoint but has **not** been verified against a live deployment in this workspace.

## Project and release files

- [Five phases](docs/PHASES.md) and [four-person workstreams](docs/WORKSTREAMS.md), with Billi carrying the largest workload.
- [Technical contract](docs/TECHNICAL_SPEC.md), [project plan](docs/PROJECT_PLAN.md), and [contributor instructions](AGENTS.md).
- [Azure deployment runbook](docs/DEPLOYMENT.md), [demo script](docs/DEMO_SCRIPT.md), and [submission checklist](docs/SUBMISSION_CHECKLIST.md).

The [public source repository](https://github.com/VIKSIT-GARG/after90) is available on GitHub. The team's supplied hackathon brief is `hackathon microsoft-1.pdf` outside this repository. The [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) set registration for October 20, 2026 at noon Pacific and submission for October 27, 2026 at 11:59 p.m. Pacific. The hosted video and working demo URL will be added after publication.

## AI delivery waves 1 and 2

The new AI service is staged separately from the legacy explanation endpoints.
See [delivery dependencies](docs/AI_DELIVERY.md), [typed contracts](docs/AI_CONTRACT.md),
[access checks](docs/AI_ACCESS.md), [evaluation](docs/AI_EVALUATION.md), and
[completion audit](docs/AI_PROGRESS.md). `backend.matchlens` remains the internal
package name for compatibility.

```sh
python scripts/check_ai_readiness.py       # Offline; exits 2 when unconfigured
python scripts/evaluate_ai.py             # Offline behavioural evaluation
python scripts/preview_ai.py --recap      # Inspect full-time context and narration
python scripts/preview_ai.py --insight-id goal-e072 --minute 29
```

Only `--live` on the readiness/preview scripts opts into a model call. A template
fallback or injected response is not proof of Foundry access. Missing credentials,
registration verification and cloud permissions remain visible external gates.
The UI/API integration, caching changes, studio preview, browser evaluation, and
public Azure release follow in phases 7-10.
