#!/usr/bin/env bash
set -euo pipefail

project="${DOPPLER_PROJECT:-rheonic}"
config="${DOPPLER_CONFIG:-stgdemo}"

if [[ $# -eq 0 ]]; then
  echo "Usage: bash tests/e2e/run_stgdemo.sh <command> [args...]" >&2
  exit 1
fi

if ! command -v doppler >/dev/null 2>&1; then
  echo "doppler CLI is required for stgdemo runs." >&2
  exit 1
fi

preserve_env="RHEONIC_PROVIDER,RHEONIC_MODEL,RHEONIC_DEMO_CASE,RHEONIC_SCENARIO,RHEONIC_STEP_SLEEP_MS,RHEONIC_RETRY_STORM_COUNT,RHEONIC_LOOP_COUNT,RHEONIC_TOKEN_EXPLOSION_TOKENS,RHEONIC_CAP_BREACH_TOKENS,RHEONIC_REQ_CAP_BREACH_COUNT,RHEONIC_CAP_BREACH_REQ_TOKENS,RHEONIC_NEAR_CAP_TOKENS,RHEONIC_MAX_TOKENS,RHEONIC_NEAR_CAP_SEED_TOKENS,RHEONIC_PROTECT_DECISION_TIMEOUT_MS,RHEONIC_ENVIRONMENT,RHEONIC_DEBUG"

exec doppler run --project "$project" --config "$config" --preserve-env="$preserve_env" -- "$@"
