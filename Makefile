.PHONY: setup test backend frontend build

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -r backend/requirements-dev.txt
	cd frontend && npm ci

test:
	.venv/bin/python -m pytest

backend:
	.venv/bin/uvicorn backend.matchlens.api:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build
