.PHONY: test test-backend test-frontend test-sdk-node test-sdk-python test-e2e check check-internal coverage coverage-backend coverage-frontend coverage-sdk-node coverage-sdk-python up-deps up-dev down-dev up-test down-test up-staging down-staging up-prod down-prod migrate-prod promtail-prod smoke-staging demo-stg-python demo-stg-node protect-stg-python protect-stg-node demo-prod-python demo-prod-node protect-prod-python protect-prod-node backend frontend sdk-node sdk-python e2e diagrams diagrams-check sync-version

DOPPLER_DEMO_PROJECT ?= rheonic
DOPPLER_STG_DEMO_CONFIG ?= stg_demo
DOPPLER_PROD_DEMO_CONFIG ?= prod_demo
RHEONIC_STEP_SLEEP_MS ?= 200
RHEONIC_RETRY_STORM_COUNT ?= 5
RHEONIC_LOOP_COUNT ?= 6
RHEONIC_TOKEN_EXPLOSION_TOKENS ?= 3300
RHEONIC_CAP_BREACH_TOKENS ?= 4000
RHEONIC_REQ_CAP_BREACH_COUNT ?= 6
RHEONIC_CAP_BREACH_REQ_TOKENS ?= 1
RHEONIC_NEAR_CAP_TOKENS ?= 3200
RHEONIC_MAX_TOKENS ?= 128
RHEONIC_PROTECT_DECISION_TIMEOUT_MS ?= 160
RHEONIC_NEAR_CAP_SEED_TOKENS ?= 1600
DEMO_STG_USAGE = make demo-stg-python RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach
PROTECT_STG_USAGE = make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown
DEMO_PROD_USAGE = make demo-prod-python RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach
PROTECT_PROD_USAGE = make protect-prod-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown

define maybe_demo_env
$(if $(filter command line environment override,$(origin $(1))),$(1)="$($(1))")
endef

up-deps:
	@bash deploy/local_doppler.sh up -d postgres redis

up-dev:
	@bash deploy/local_doppler.sh up -d --build postgres redis db_init backend worker scheduler frontend

down-dev:
	@bash deploy/local_doppler.sh down

up-test:
	@docker compose -p rheonic_test -f docker-compose.test.yml up -d --build

down-test:
	@docker compose -p rheonic_test -f docker-compose.test.yml down -v

up-staging:
	@bash deploy/staging_doppler.sh up -d --build

down-staging:
	@bash deploy/staging_doppler.sh down

up-prod:
	@bash deploy/prod_doppler.sh up -d --build

down-prod:
	@bash deploy/prod_doppler.sh down

migrate-prod:
	@bash deploy/prod_migrate.sh

promtail-prod:
	@bash deploy/prod_promtail.sh up -d

sync-version:
	@python3 scripts/sync_version.py

smoke-staging:
	@bash -lc "set -euo pipefail; bash deploy/staging_doppler.sh ps; bash deploy/staging_doppler.sh exec backend python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)\" >/dev/null; bash deploy/staging_doppler.sh exec backend python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)\" >/dev/null; bash deploy/staging_doppler.sh logs --tail=80 backend worker scheduler"

demo-stg-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_STG_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="demo-stg-python" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_DEMO_CASE) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_TOKENS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh python3 tests/e2e/python/demo.py'

demo-stg-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_STG_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="demo-stg-node" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_DEMO_CASE) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_TOKENS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh node tests/e2e/node/demo.mjs'

protect-stg-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_STG_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="protect-stg-python" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_SCENARIO) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_MAX_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_SEED_TOKENS) $(call maybe_demo_env,RHEONIC_PROTECT_DECISION_TIMEOUT_MS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh python3 tests/e2e/python/demo_protect.py'

protect-stg-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_STG_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="protect-stg-node" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_SCENARIO) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_MAX_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_SEED_TOKENS) $(call maybe_demo_env,RHEONIC_PROTECT_DECISION_TIMEOUT_MS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh node tests/e2e/node/demo_protect.mjs'

demo-prod-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(DEMO_PROD_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(DEMO_PROD_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: $(DEMO_PROD_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_PROD_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="demo-prod-python" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_DEMO_CASE) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_TOKENS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh python3 tests/e2e/python/demo.py'

demo-prod-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make demo-prod-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make demo-prod-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: make demo-prod-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_PROD_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="demo-prod-node" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_DEMO_CASE) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_TOKENS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh node tests/e2e/node/demo.mjs'

protect-prod-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(PROTECT_PROD_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(PROTECT_PROD_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: $(PROTECT_PROD_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_PROD_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="protect-prod-python" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_SCENARIO) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_MAX_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_SEED_TOKENS) $(call maybe_demo_env,RHEONIC_PROTECT_DECISION_TIMEOUT_MS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh python3 tests/e2e/python/demo_protect.py'

protect-prod-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make protect-prod-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make protect-prod-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: make protect-prod-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_PROD_DEMO_CONFIG)" RHEONIC_DEMO_TARGET_HINT="protect-prod-node" $(call maybe_demo_env,RHEONIC_PROVIDER) $(call maybe_demo_env,RHEONIC_MODEL) $(call maybe_demo_env,RHEONIC_SCENARIO) $(call maybe_demo_env,RHEONIC_STEP_SLEEP_MS) $(call maybe_demo_env,RHEONIC_RETRY_STORM_COUNT) $(call maybe_demo_env,RHEONIC_LOOP_COUNT) $(call maybe_demo_env,RHEONIC_TOKEN_EXPLOSION_TOKENS) $(call maybe_demo_env,RHEONIC_CAP_BREACH_TOKENS) $(call maybe_demo_env,RHEONIC_REQ_CAP_BREACH_COUNT) $(call maybe_demo_env,RHEONIC_CAP_BREACH_REQ_TOKENS) $(call maybe_demo_env,RHEONIC_MAX_TOKENS) $(call maybe_demo_env,RHEONIC_NEAR_CAP_SEED_TOKENS) $(call maybe_demo_env,RHEONIC_PROTECT_DECISION_TIMEOUT_MS) $(call maybe_demo_env,RHEONIC_ENVIRONMENT) $(call maybe_demo_env,RHEONIC_DEBUG) $(call maybe_demo_env,RHEONIC_BACKEND_URL) $(call maybe_demo_env,RHEONIC_BASE_URL) $(call maybe_demo_env,RHEONIC_INGEST_KEY) $(call maybe_demo_env,RHEONIC_PROJECT_ID) $(call maybe_demo_env,RHEONIC_AUTH_EMAIL) $(call maybe_demo_env,RHEONIC_AUTH_PASSWORD) $(call maybe_demo_env,RHEONIC_PROVIDER_URL) bash tests/e2e/run_demo.sh node tests/e2e/node/demo_protect.mjs'

ifneq ($(filter backend frontend sdk-node sdk-python test-backend test-frontend test-sdk-node test-sdk-python,$(MAKECMDGOALS)),)
test:
	@:
else
test: test-backend test-sdk-node test-sdk-python test-frontend
endif

test-e2e:
	@echo "Running isolated e2e with project rheonic_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p rheonic_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p rheonic_test -f docker-compose.test.yml up -d --build postgres_test redis_test backend_test provider_stub_test >/dev/null; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_node_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/node protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_python_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/python protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'"

check:
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --build --rm check_test"

check-internal:
	@ruff check .
	@ruff format --check .
	@mypy
	@npm run -s lint:eslint
	@npm run -s lint:tsc
	@npm run -s lint:style
	@hadolint $$(find . -name 'Dockerfile*' -not -path '*/node_modules/*')
	@npm run -s lint:dup

coverage: coverage-backend coverage-sdk-node coverage-sdk-python coverage-frontend

coverage-backend:
	@echo "Running backend tests with coverage"
	@bash -lc "set -euo pipefail; trap 'docker compose -p rheonic_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p rheonic_test -f docker-compose.test.yml up -d --build postgres_test redis_test backend_test >/dev/null; docker compose -p rheonic_test -f docker-compose.test.yml run --rm -v \"$$(pwd):/workspace\" backend_test sh -lc \"cd /workspace/backend && pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80\""

coverage-sdk-node:
	@echo "Running sdk-node tests with coverage"
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_node_unit"

coverage-sdk-python:
	@echo "Running sdk-python tests with coverage"
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_python_unit"

coverage-frontend:
	@echo "Running frontend tests with coverage"
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm frontend_test"

test-backend:
	@echo "Running isolated backend tests with project rheonic_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p rheonic_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p rheonic_test -f docker-compose.test.yml up -d --build postgres_test redis_test backend_test >/dev/null; docker compose -p rheonic_test -f docker-compose.test.yml run --rm -v \"$$(pwd):/workspace\" backend_test sh -lc \"cd /workspace/backend && pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80\" 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

test-sdk-node:
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_node_unit 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^# Subtest:/) sub(/^# Subtest:/, \"\\033[36m# Subtest:\\033[0m\"); if (/^# pass /) sub(/^# pass /, \"# \\033[32mpass \\033[0m\"); if (/^# fail /) sub(/^# fail /, \"# \\033[31mfail \\033[0m\"); if (/^# tests / || /^# duration_ms / || /^1\\.\\./) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); if (/^All files[[:space:]]*\\|/ || /^-----------------------------\\|/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'; echo '\033[32msdk-node tests PASSED\033[0m'; echo '\033[32msdk-node coverage target PASSED (>=80%)\033[0m'"

test-sdk-python:
	@bash -lc "set -o pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_python_unit 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

test-frontend:
	@bash -lc "set -euo pipefail; docker compose -p rheonic_test -f docker-compose.test.yml run --rm frontend_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^ ✓ /) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); if (/^ ❯ /) sub(/^.*$$/, \"\\033[31m&\\033[0m\"); if (/^ Test Files / || /^      Tests /) {gsub(/([0-9]+) passed/, \"\\033[32m&\\033[0m\"); gsub(/([0-9]+) failed/, \"\\033[31m&\\033[0m\");} gsub(/frontend_build/, \"\\033[36mfrontend_build\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); print}'; echo '\033[32mfrontend tests PASSED\033[0m'; echo '\033[32mfrontend coverage target PASSED (>=80%)\033[0m'"

backend: test-backend

frontend: test-frontend

sdk-node: test-sdk-node

sdk-python: test-sdk-python

e2e: test-e2e

diagrams:
	@docker run --rm -v "$$(pwd):/work" -w /work terrastruct/d2 docs/architecture/incident_flow.d2 frontend/public/docs/architecture/incident_flow.svg
	@docker run --rm -v "$$(pwd):/work" -w /work terrastruct/d2 docs/architecture/protect_decision_flow.d2 frontend/public/docs/architecture/protect_decision_flow.svg
	@python3 docs/architecture/normalize_diagram_svgs.py

diagrams-check:
	@test -s frontend/public/docs/architecture/incident_flow.svg
	@test -s frontend/public/docs/architecture/protect_decision_flow.svg
