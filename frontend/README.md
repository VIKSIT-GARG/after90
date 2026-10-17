# MatchLens frontend

Phase 1 React + TypeScript shell for a fictional football match companion. It displays no match results or replay controls yet. Phase 2 provides the synthetic fixture and snapshot API; the interactive dashboard belongs to Phase 3.

## Local development

Requires Node.js 20.19+ or 22.12+ and npm.

```bash
cd frontend
npm install
npm run dev
```

Open the local address printed by Vite. The development server proxies `/api` to `http://localhost:8000` for later integration. The shell currently makes no API requests and works without the backend.

## Build

```bash
cd frontend
npm run build
```

The build includes TypeScript checking and writes static files to `dist/`.
