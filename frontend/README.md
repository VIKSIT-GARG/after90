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
