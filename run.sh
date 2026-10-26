#!/usr/bin/env bash
# Build and serve After90 locally. Missing Foundry settings use labelled fallback.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r backend/requirements.txt
if [[ ! -d frontend/node_modules ]]; then
  npm ci --prefix frontend
fi
npm run build --prefix frontend
exec .venv/bin/python -m uvicorn backend.matchlens.api:app \
  --host "${AFTER90_HOST:-127.0.0.1}" --port "${PORT:-8000}"
