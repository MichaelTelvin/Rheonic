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

exec doppler run --project "$project" --config "$config" -- "$@"
