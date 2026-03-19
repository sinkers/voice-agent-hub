.PHONY: test lint lint-fix build-frontend smoke-test integration-test test-all ci

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

_AGENT_ENV := $(or $(AGENT_REPO),$(HOME)/Documents/livekit-agent)/.env
_env = $(shell grep -s "^$(1)=" $(_AGENT_ENV) | cut -d= -f2-)

smoke-test:
	HUB_SECRET=$(or $(HUB_SECRET),6c20986d23d3010a2ed87b3f72c6eb63b4eaf62d88570056d598fd068ad22145) \
	LIVEKIT_URL=$(or $(LIVEKIT_URL),$(call _env,LIVEKIT_URL)) \
	LIVEKIT_API_KEY=$(or $(LIVEKIT_API_KEY),$(call _env,LIVEKIT_API_KEY)) \
	LIVEKIT_API_SECRET=$(or $(LIVEKIT_API_SECRET),$(call _env,LIVEKIT_API_SECRET)) \
	DEEPGRAM_API_KEY=$(or $(DEEPGRAM_API_KEY),$(call _env,DEEPGRAM_API_KEY)) \
	OPENAI_API_KEY=$(or $(OPENAI_API_KEY),$(call _env,OPENAI_API_KEY)) \
	uv run python tests/smoke_test.py

integration-test:
	uv run pytest tests/integration/ -v

test-all: ci integration-test
