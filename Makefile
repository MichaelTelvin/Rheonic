.PHONY: test test-backend test-frontend test-sdk-node test-sdk-python test-e2e up-deps up-dev down-dev up-test down-test backend frontend sdk-node sdk-python e2e diagrams diagrams-check

up-deps:
	@docker compose up -d postgres redis

up-dev:
	@docker compose up -d --build

down-dev:
	@docker compose down

up-test:
	@docker compose -p llmtbg_test -f docker-compose.test.yml up -d --build

down-test:
	@docker compose -p llmtbg_test -f docker-compose.test.yml down -v

ifneq ($(filter backend frontend sdk-node sdk-python test-backend test-frontend test-sdk-node test-sdk-python,$(MAKECMDGOALS)),)
test:
	@:
else
test: test-backend test-sdk-node test-sdk-python test-frontend
endif

test-e2e:
	@echo "Running isolated e2e with project llmtbg_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p llmtbg_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p llmtbg_test -f docker-compose.test.yml up -d --build postgres_test redis_test backend_test provider_stub_test >/dev/null; docker compose -p llmtbg_test -f docker-compose.test.yml run --rm sdk_node_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/node protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'; docker compose -p llmtbg_test -f docker-compose.test.yml run --rm sdk_python_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/python protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'"

test-backend:
	@echo "Running isolated backend tests with project llmtbg_test using docker-compose.test.yml"
	@bash -lc "set -euo pipefail; trap 'docker compose -p llmtbg_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p llmtbg_test -f docker-compose.test.yml up -d postgres_test redis_test backend_test >/dev/null; docker compose -p llmtbg_test -f docker-compose.test.yml run --rm -v \"$$(pwd):/workspace\" backend_test pytest -v 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

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
	@docker run --rm -v "$$(pwd):/work" -w /work terrastruct/d2 docs/architecture/incident_flow.d2 docs/architecture/incident_flow.svg
	@docker run --rm -v "$$(pwd):/work" -w /work terrastruct/d2 docs/architecture/protect_decision_flow.d2 docs/architecture/protect_decision_flow.svg
	@python3 docs/architecture/normalize_diagram_svgs.py
	@cp docs/architecture/incident_flow.svg frontend/public/architecture/incident_flow.svg
	@cp docs/architecture/protect_decision_flow.svg frontend/public/architecture/protect_decision_flow.svg

diagrams-check:
	@test -s docs/architecture/incident_flow.svg
	@test -s docs/architecture/protect_decision_flow.svg
