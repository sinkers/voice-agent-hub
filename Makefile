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
ifndef HUB_SECRET
	$(error HUB_SECRET environment variable must be set for smoke tests)
endif
ifeq ($(and $(LIVEKIT_URL)$(call _env,LIVEKIT_URL)),)
	$(error LIVEKIT_URL must be set either in environment or in agent .env file)
endif
ifeq ($(and $(LIVEKIT_API_KEY)$(call _env,LIVEKIT_API_KEY)),)
	$(error LIVEKIT_API_KEY must be set either in environment or in agent .env file)
endif
ifeq ($(and $(LIVEKIT_API_SECRET)$(call _env,LIVEKIT_API_SECRET)),)
	$(error LIVEKIT_API_SECRET must be set either in environment or in agent .env file)
endif
	HUB_SECRET=$(HUB_SECRET) \
	LIVEKIT_URL=$(or $(LIVEKIT_URL),$(call _env,LIVEKIT_URL)) \
	LIVEKIT_API_KEY=$(or $(LIVEKIT_API_KEY),$(call _env,LIVEKIT_API_KEY)) \
	LIVEKIT_API_SECRET=$(or $(LIVEKIT_API_SECRET),$(call _env,LIVEKIT_API_SECRET)) \
	DEEPGRAM_API_KEY=$(or $(DEEPGRAM_API_KEY),$(call _env,DEEPGRAM_API_KEY)) \
	OPENAI_API_KEY=$(or $(OPENAI_API_KEY),$(call _env,OPENAI_API_KEY)) \
	uv run python tests/smoke_test.py

_AGENT_ENV := $(or $(AGENT_REPO),$(HOME)/Documents/livekit-agent)/.env
_env = $(shell grep -s "^$(1)=" $(_AGENT_ENV) | cut -d= -f2-)

integration-test:
ifndef HUB_SECRET
	$(error HUB_SECRET environment variable must be set for integration tests)
endif
ifeq ($(and $(LIVEKIT_URL)$(call _env,LIVEKIT_URL)),)
	$(error LIVEKIT_URL must be set either in environment or in agent .env file)
endif
ifeq ($(and $(LIVEKIT_API_KEY)$(call _env,LIVEKIT_API_KEY)),)
	$(error LIVEKIT_API_KEY must be set either in environment or in agent .env file)
endif
ifeq ($(and $(LIVEKIT_API_SECRET)$(call _env,LIVEKIT_API_SECRET)),)
	$(error LIVEKIT_API_SECRET must be set either in environment or in agent .env file)
endif
	HUB_SECRET=$(HUB_SECRET) \
	LIVEKIT_URL=$(or $(LIVEKIT_URL),$(call _env,LIVEKIT_URL)) \
	LIVEKIT_API_KEY=$(or $(LIVEKIT_API_KEY),$(call _env,LIVEKIT_API_KEY)) \
	LIVEKIT_API_SECRET=$(or $(LIVEKIT_API_SECRET),$(call _env,LIVEKIT_API_SECRET)) \
	DEEPGRAM_API_KEY=$(or $(DEEPGRAM_API_KEY),$(call _env,DEEPGRAM_API_KEY)) \
	OPENAI_API_KEY=$(or $(OPENAI_API_KEY),$(call _env,OPENAI_API_KEY)) \
	uv run pytest tests/integration/ -v

test-all: ci integration-test
