#!/usr/bin/env bash
set -euo pipefail

project="${DOPPLER_PROJECT:-rheonic}"
config="${DOPPLER_CONFIG:-stgdemo}"

if [[ $# -eq 0 ]]; then
  echo "Usage: bash tests/e2e/run_demo.sh <command> [args...]" >&2
  exit 1
fi

if ! command -v doppler >/dev/null 2>&1; then
  echo "doppler CLI is required for demo runs." >&2
  exit 1
fi

preserve_env="RHEONIC_PROVIDER,RHEONIC_MODEL,RHEONIC_DEMO_CASE,RHEONIC_SCENARIO,RHEONIC_STEP_SLEEP_MS,RHEONIC_RETRY_STORM_COUNT,RHEONIC_LOOP_COUNT,RHEONIC_TOKEN_EXPLOSION_TOKENS,RHEONIC_CAP_BREACH_TOKENS,RHEONIC_REQ_CAP_BREACH_COUNT,RHEONIC_CAP_BREACH_REQ_TOKENS,RHEONIC_NEAR_CAP_TOKENS,RHEONIC_MAX_TOKENS,RHEONIC_NEAR_CAP_SEED_TOKENS,RHEONIC_PROTECT_DECISION_TIMEOUT_MS,RHEONIC_ENVIRONMENT,RHEONIC_DEBUG,RHEONIC_BACKEND_URL,RHEONIC_BASE_URL,RHEONIC_INGEST_KEY,RHEONIC_PROJECT_ID,RHEONIC_AUTH_EMAIL,RHEONIC_AUTH_PASSWORD,RHEONIC_PROVIDER_URL,RHEONIC_DEMO_TARGET_HINT,RHEONIC_VERBOSE"
IFS=',' read -r -a preserve_candidates <<< "$preserve_env"
override_env=()
for var_name in "${preserve_candidates[@]}"; do
  if [[ -n "${!var_name+x}" ]]; then
    if [[ -z "${!var_name}" ]]; then
      unset "$var_name"
      continue
    fi
    override_env+=("${var_name}=${!var_name}")
    unset "$var_name"
  fi
done

if [[ ${#override_env[@]} -gt 0 ]]; then
  doppler run --project "$project" --config "$config" -- env "${override_env[@]}" "$@"
else
  doppler run --project "$project" --config "$config" -- "$@"
fi
