#!/usr/bin/env bash
set -euo pipefail

token_file="${DOPPLER_TOKEN_FILE:-$HOME/.config/rheonic/doppler.env}"
project="${DOPPLER_PROJECT:-rheonic}"
config="${DOPPLER_CONFIG:-dev}"

if [[ -z "${DOPPLER_TOKEN:-}" && -f "$token_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$token_file"
  set +a
fi

if [[ -z "${DOPPLER_TOKEN:-}" ]]; then
  echo "DOPPLER_TOKEN is required. Set it directly or provide $token_file." >&2
  exit 1
fi

exec doppler run --token "$DOPPLER_TOKEN" --project "$project" --config "$config" -- docker compose -f docker-compose.yml "$@"
