#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

token_file="${DOPPLER_TOKEN_FILE:-$HOME/.config/rheonic/doppler.prod.env}"
project="${DOPPLER_PROJECT:-rheonic}"
config="${DOPPLER_CONFIG:-prod}"

if [[ -z "${DOPPLER_TOKEN:-}" && ! -f "$token_file" && -f "$HOME/.config/rheonic/doppler.env" ]]; then
  token_file="$HOME/.config/rheonic/doppler.env"
fi

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

version_value="$(tr -d '[:space:]' < "${ROOT_DIR}/VERSION")"
export APP_VERSION="$version_value"
export VITE_APP_VERSION="$version_value"

doppler run --token "$DOPPLER_TOKEN" --project "$project" --config "$config" -- \
  docker compose -p rheonic_prod -f docker-compose.prod.yml up -d postgres redis

doppler run --token "$DOPPLER_TOKEN" --project "$project" --config "$config" -- \
  docker compose -p rheonic_prod -f docker-compose.prod.yml run --rm db_init
