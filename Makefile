.PHONY: setup test backend frontend build ai-evaluate ai-readiness ai-preview integration-test browser-test

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

ai-evaluate:
	.venv/bin/python scripts/evaluate_ai.py

ai-readiness:
	.venv/bin/python scripts/check_ai_readiness.py

ai-preview:
	.venv/bin/python scripts/preview_ai.py --recap

integration-test:
	.venv/bin/python scripts/evaluate_integrated.py

browser-test:
	.venv/bin/python scripts/test_browser.py
