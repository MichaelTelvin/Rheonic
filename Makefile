.PHONY: test test-backend test-frontend test-sdk-node test-sdk-python test-e2e up-deps up-dev down-dev up-test down-test up-staging down-staging up-prod down-prod smoke-staging demo-stg-python demo-stg-node protect-stg-python protect-stg-node backend frontend sdk-node sdk-python e2e diagrams diagrams-check

DOPPLER_DEMO_PROJECT ?= rheonic
DOPPLER_DEMO_CONFIG ?= stgdemo
RHEONIC_STEP_SLEEP_MS ?= 200
RHEONIC_RETRY_STORM_COUNT ?= 6
RHEONIC_LOOP_COUNT ?= 7
RHEONIC_TOKEN_EXPLOSION_TOKENS ?= 9000
RHEONIC_CAP_BREACH_TOKENS ?= 4000
RHEONIC_REQ_CAP_BREACH_COUNT ?= 6
RHEONIC_CAP_BREACH_REQ_TOKENS ?= 1
RHEONIC_NEAR_CAP_TOKENS ?= 3200
RHEONIC_MAX_TOKENS ?= 128
RHEONIC_NEAR_CAP_SEED_TOKENS ?= 1600
DEMO_STG_USAGE = make demo-stg-python RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach
PROTECT_STG_USAGE = make protect-stg-python RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown

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
	@docker compose -f docker-compose.prod.yml up -d --build

down-prod:
	@docker compose -f docker-compose.prod.yml down

smoke-staging:
	@bash -lc "set -euo pipefail; bash deploy/staging_doppler.sh ps; bash deploy/staging_doppler.sh exec backend python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)\" >/dev/null; bash deploy/staging_doppler.sh exec backend python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)\" >/dev/null; bash deploy/staging_doppler.sh logs --tail=80 backend worker scheduler"

demo-stg-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: $(DEMO_STG_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_DEMO_CONFIG)" RHEONIC_PROVIDER="$(RHEONIC_PROVIDER)" RHEONIC_MODEL="$(RHEONIC_MODEL)" RHEONIC_DEMO_CASE="$(RHEONIC_DEMO_CASE)" RHEONIC_STEP_SLEEP_MS="$(RHEONIC_STEP_SLEEP_MS)" RHEONIC_RETRY_STORM_COUNT="$(RHEONIC_RETRY_STORM_COUNT)" RHEONIC_LOOP_COUNT="$(RHEONIC_LOOP_COUNT)" RHEONIC_TOKEN_EXPLOSION_TOKENS="$(RHEONIC_TOKEN_EXPLOSION_TOKENS)" RHEONIC_CAP_BREACH_TOKENS="$(RHEONIC_CAP_BREACH_TOKENS)" RHEONIC_REQ_CAP_BREACH_COUNT="$(RHEONIC_REQ_CAP_BREACH_COUNT)" RHEONIC_CAP_BREACH_REQ_TOKENS="$(RHEONIC_CAP_BREACH_REQ_TOKENS)" RHEONIC_NEAR_CAP_TOKENS="$(RHEONIC_NEAR_CAP_TOKENS)" $(if $(RHEONIC_ENVIRONMENT),RHEONIC_ENVIRONMENT="$(RHEONIC_ENVIRONMENT)") $(if $(RHEONIC_DEBUG),RHEONIC_DEBUG="$(RHEONIC_DEBUG)") bash tests/e2e/run_stgdemo.sh python3 tests/e2e/python/demo.py'

demo-stg-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; test -n "$(RHEONIC_DEMO_CASE)" || { echo "RHEONIC_DEMO_CASE is required. Example: make demo-stg-node RHEONIC_PROVIDER=google RHEONIC_MODEL=gemini-1.5-pro RHEONIC_DEMO_CASE=req_cap_breach" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_DEMO_CONFIG)" RHEONIC_PROVIDER="$(RHEONIC_PROVIDER)" RHEONIC_MODEL="$(RHEONIC_MODEL)" RHEONIC_DEMO_CASE="$(RHEONIC_DEMO_CASE)" RHEONIC_STEP_SLEEP_MS="$(RHEONIC_STEP_SLEEP_MS)" RHEONIC_RETRY_STORM_COUNT="$(RHEONIC_RETRY_STORM_COUNT)" RHEONIC_LOOP_COUNT="$(RHEONIC_LOOP_COUNT)" RHEONIC_TOKEN_EXPLOSION_TOKENS="$(RHEONIC_TOKEN_EXPLOSION_TOKENS)" RHEONIC_CAP_BREACH_TOKENS="$(RHEONIC_CAP_BREACH_TOKENS)" RHEONIC_REQ_CAP_BREACH_COUNT="$(RHEONIC_REQ_CAP_BREACH_COUNT)" RHEONIC_CAP_BREACH_REQ_TOKENS="$(RHEONIC_CAP_BREACH_REQ_TOKENS)" RHEONIC_NEAR_CAP_TOKENS="$(RHEONIC_NEAR_CAP_TOKENS)" $(if $(RHEONIC_ENVIRONMENT),RHEONIC_ENVIRONMENT="$(RHEONIC_ENVIRONMENT)") $(if $(RHEONIC_DEBUG),RHEONIC_DEBUG="$(RHEONIC_DEBUG)") bash tests/e2e/run_stgdemo.sh node tests/e2e/node/demo.mjs'

protect-stg-python:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: $(PROTECT_STG_USAGE)" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_DEMO_CONFIG)" RHEONIC_PROVIDER="$(RHEONIC_PROVIDER)" RHEONIC_MODEL="$(RHEONIC_MODEL)" RHEONIC_SCENARIO="$(RHEONIC_SCENARIO)" RHEONIC_STEP_SLEEP_MS="$(RHEONIC_STEP_SLEEP_MS)" RHEONIC_RETRY_STORM_COUNT="$(RHEONIC_RETRY_STORM_COUNT)" RHEONIC_LOOP_COUNT="$(RHEONIC_LOOP_COUNT)" RHEONIC_TOKEN_EXPLOSION_TOKENS="$(RHEONIC_TOKEN_EXPLOSION_TOKENS)" RHEONIC_CAP_BREACH_TOKENS="$(RHEONIC_CAP_BREACH_TOKENS)" RHEONIC_REQ_CAP_BREACH_COUNT="$(RHEONIC_REQ_CAP_BREACH_COUNT)" RHEONIC_CAP_BREACH_REQ_TOKENS="$(RHEONIC_CAP_BREACH_REQ_TOKENS)" RHEONIC_MAX_TOKENS="$(RHEONIC_MAX_TOKENS)" RHEONIC_NEAR_CAP_SEED_TOKENS="$(RHEONIC_NEAR_CAP_SEED_TOKENS)" $(if $(RHEONIC_PROTECT_DECISION_TIMEOUT_MS),RHEONIC_PROTECT_DECISION_TIMEOUT_MS="$(RHEONIC_PROTECT_DECISION_TIMEOUT_MS)") $(if $(RHEONIC_ENVIRONMENT),RHEONIC_ENVIRONMENT="$(RHEONIC_ENVIRONMENT)") $(if $(RHEONIC_DEBUG),RHEONIC_DEBUG="$(RHEONIC_DEBUG)") bash tests/e2e/run_stgdemo.sh python3 tests/e2e/python/demo_protect.py'

protect-stg-node:
	@bash -lc 'set -euo pipefail; test -n "$(RHEONIC_PROVIDER)" || { echo "RHEONIC_PROVIDER is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_MODEL)" || { echo "RHEONIC_MODEL is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; test -n "$(RHEONIC_SCENARIO)" || { echo "RHEONIC_SCENARIO is required. Example: make protect-stg-node RHEONIC_PROVIDER=openai RHEONIC_MODEL=gpt-4o-mini RHEONIC_SCENARIO=cooldown" >&2; exit 1; }; env DOPPLER_PROJECT="$(DOPPLER_DEMO_PROJECT)" DOPPLER_CONFIG="$(DOPPLER_DEMO_CONFIG)" RHEONIC_PROVIDER="$(RHEONIC_PROVIDER)" RHEONIC_MODEL="$(RHEONIC_MODEL)" RHEONIC_SCENARIO="$(RHEONIC_SCENARIO)" RHEONIC_STEP_SLEEP_MS="$(RHEONIC_STEP_SLEEP_MS)" RHEONIC_RETRY_STORM_COUNT="$(RHEONIC_RETRY_STORM_COUNT)" RHEONIC_LOOP_COUNT="$(RHEONIC_LOOP_COUNT)" RHEONIC_TOKEN_EXPLOSION_TOKENS="$(RHEONIC_TOKEN_EXPLOSION_TOKENS)" RHEONIC_CAP_BREACH_TOKENS="$(RHEONIC_CAP_BREACH_TOKENS)" RHEONIC_REQ_CAP_BREACH_COUNT="$(RHEONIC_REQ_CAP_BREACH_COUNT)" RHEONIC_CAP_BREACH_REQ_TOKENS="$(RHEONIC_CAP_BREACH_REQ_TOKENS)" RHEONIC_MAX_TOKENS="$(RHEONIC_MAX_TOKENS)" RHEONIC_NEAR_CAP_SEED_TOKENS="$(RHEONIC_NEAR_CAP_SEED_TOKENS)" $(if $(RHEONIC_PROTECT_DECISION_TIMEOUT_MS),RHEONIC_PROTECT_DECISION_TIMEOUT_MS="$(RHEONIC_PROTECT_DECISION_TIMEOUT_MS)") $(if $(RHEONIC_ENVIRONMENT),RHEONIC_ENVIRONMENT="$(RHEONIC_ENVIRONMENT)") $(if $(RHEONIC_DEBUG),RHEONIC_DEBUG="$(RHEONIC_DEBUG)") bash tests/e2e/run_stgdemo.sh node tests/e2e/node/demo_protect.mjs'

ifneq ($(filter backend frontend sdk-node sdk-python test-backend test-frontend test-sdk-node test-sdk-python,$(MAKECMDGOALS)),)
test:
	@:
else
test: test-backend test-sdk-node test-sdk-python test-frontend
endif

test-e2e:
	@echo "Running isolated e2e with project rheonic_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p rheonic_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p rheonic_test -f docker-compose.test.yml up -d --build postgres_test redis_test backend_test provider_stub_test >/dev/null; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_node_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/node protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'; docker compose -p rheonic_test -f docker-compose.test.yml run --rm sdk_python_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/python protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'"

test-backend:
	@echo "Running isolated backend tests with project rheonic_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p rheonic_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p rheonic_test -f docker-compose.test.yml up -d postgres_test redis_test backend_test >/dev/null; docker compose -p rheonic_test -f docker-compose.test.yml run --rm -v \"$$(pwd):/workspace\" backend_test sh -lc \"cd /workspace/backend && pytest -v\" 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

test-sdk-node:
	@bash -lc "set -o pipefail; docker compose run --rm sdk_node 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^✔ /) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); if (/^ℹ pass /) sub(/pass/, \"\\033[32mpass\\033[0m\"); if (/^ℹ fail /) sub(/fail/, \"\\033[31mfail\\033[0m\"); print}'"

test-sdk-python:
	@bash -lc "set -o pipefail; docker compose run --rm sdk_python 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

test-frontend:
	@bash -lc "set -o pipefail; docker compose run --rm frontend_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^ ✓ /) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); if (/^ ❯ /) sub(/^.*$$/, \"\\033[31m&\\033[0m\"); if (/^ Test Files / || /^      Tests /) {gsub(/([0-9]+) passed/, \"\\033[32m&\\033[0m\"); gsub(/([0-9]+) failed/, \"\\033[31m&\\033[0m\");} gsub(/frontend_build/, \"\\033[36mfrontend_build\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); print}'"

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
