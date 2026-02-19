.PHONY: test test-backend test-frontend test-sdk-node test-sdk-python test-e2e up-deps backend frontend sdk-node sdk-python e2e

up-deps:
	@docker compose up -d postgres redis

ifneq ($(filter backend frontend sdk-node sdk-python test-backend test-frontend test-sdk-node test-sdk-python,$(MAKECMDGOALS)),)
test:
	@:
else
test: test-backend test-sdk-node test-sdk-python test-frontend
endif

test-e2e:
	@bash -lc "set -euo pipefail; trap 'docker compose -p llmtbg_test -f docker-compose.test.yml down -v >/dev/null 2>&1 || true' EXIT; docker compose -p llmtbg_test -f docker-compose.test.yml up -d --build >/dev/null; docker compose -p llmtbg_test -f docker-compose.test.yml run --rm sdk_node_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/node protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'; docker compose -p llmtbg_test -f docker-compose.test.yml run --rm sdk_python_test 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); if (/python protect e2e/) sub(/^.*$$/, \"\\033[36m&\\033[0m\"); print}'"

test-backend:
	@bash -lc "set -o pipefail; docker compose run --rm backend pytest -v 2>&1 | sed '/^ Container /d;/^\\[+\\]/d' | awk '{if (/^[^ ]+::[^ ]+/) sub(/^([^ ]+::[^ ]+)/, \"\\033[36m&\\033[0m\"); gsub(/PASSED/, \"\\033[32mPASSED\\033[0m\"); gsub(/FAILED/, \"\\033[31mFAILED\\033[0m\"); gsub(/ERROR/, \"\\033[31mERROR\\033[0m\"); print}'"

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
