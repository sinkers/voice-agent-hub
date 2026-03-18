.PHONY: test lint lint-fix build-frontend smoke-test test-all ci

test:
	uv run pytest tests/ -v

lint:
	uv run ruff check backend/ tests/
	cd frontend && npm run build

lint-fix:
	uv run ruff check backend/ tests/ --fix

build-frontend:
	cd frontend && npm ci && npm run build

# Run all checks exactly as CI would — use this before pushing
ci:
	uv run pytest tests/ -v
	uv run ruff check backend/ tests/
	cd frontend && npm ci && npm run build

# Requires: HUB_TOKEN, AGENT_ID, OPENAI_API_KEY (optional)
smoke-test:
	uv run python tests/smoke_test.py

test-all: ci smoke-test
