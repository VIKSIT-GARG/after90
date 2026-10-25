# MatchLens frontend

React and TypeScript dashboard for the fictional MatchLens fixture. It requests snapshots, insight explanations, and recap from the FastAPI backend, and labels the data as synthetic. The browser controls the replay minute; the API computes each snapshot independently.

## Local development

Start the backend with `make backend` from the repository root. Requires Node.js 22+ and npm.

```bash
cd frontend
npm ci
npm run dev
```

Open the local address printed by Vite. The development server proxies `/api` to `http://localhost:8000`.

## Build

```bash
cd frontend
npm run build
```

The build includes TypeScript checking and writes static files to `dist/`. The root Dockerfile packages those files with the API.

## Activity timeline checks

Run `npm test` for activity scoring, inclusive bucket boundaries, final-minute events,
and preview/API rolling-window parity. `npm run build` checks TypeScript and production bundling.
The timeline shows only supplied minutes (`minute - 9` through `minute`, inclusive),
clips partial edge intervals, and includes minute 90 in the final 85–90 interval.
During API loading it retains the previous activity panel, labelled with its snapshot
minute, so interval selection and keyboard focus survive seeking. Switching data
sources resets that panel.

## Integrated narrative experience

The UI consumes bounded-narrative HTTP responses with headline, exact analyst
facts, limitations, provenance and an overlay. Template responses are not pinned
in the browser cache; Refresh retries after the server's short failure cache.
Real browser checks: `python scripts/test_browser.py` from the repository root,
after installing Playwright Chromium. It starts a local server and strips model
credentials from the test environment. Browser evidence is test output, not live
Foundry evaluation.

Optional team prioritization: build with `VITE_ENABLE_TEAM_FOCUS=true`. This
feature is default-disabled pending the public-release gate. It changes story
order only; all facts, evidence and insight records remain intact.
