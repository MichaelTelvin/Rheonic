#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

token_file="${DOPPLER_TOKEN_FILE:-$HOME/.config/rheonic/doppler.stg.env}"
project="${DOPPLER_PROJECT:-rheonic}"
config="${DOPPLER_CONFIG:-stg}"

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

app_compose=(docker compose -p rheonic_staging -f deploy/docker-compose.staging.yml)
proxy_compose=(docker compose -p rheonic_proxy -f deploy/docker-compose.proxy.yml)
command="${1:-up}"

run_app() {
  doppler run --token "$DOPPLER_TOKEN" --project "$project" --config "$config" -- "${app_compose[@]}" "$@"
}

run_proxy() {
  "${proxy_compose[@]}" "$@"
}

case "$command" in
  up)
    docker network create rheonic_staging_edge >/dev/null 2>&1 || true
    docker network create rheonic_prod_edge >/dev/null 2>&1 || true
    run_app "$@"
    run_proxy up -d caddy
    ;;
  ps)
    run_app ps
    echo
    run_proxy ps caddy
    ;;
  logs)
    shift || true
    if [[ "${1:-}" == "caddy" || "${2:-}" == "caddy" ]]; then
      run_proxy logs "$@"
    else
      run_app logs "$@"
    fi
    ;;
  exec)
    shift || true
    if [[ "${1:-}" == "caddy" ]]; then
      run_proxy exec "$@"
    else
      run_app exec "$@"
    fi
    ;;
  restart)
    shift || true
    if [[ "${1:-}" == "caddy" ]]; then
      run_proxy restart caddy
    else
      docker network create rheonic_staging_edge >/dev/null 2>&1 || true
      docker network create rheonic_prod_edge >/dev/null 2>&1 || true
      run_app restart "$@"
      run_proxy up -d caddy
    fi
    ;;
  down)
    run_app down "${@:2}"
    ;;
  *)
    run_app "$@"
    ;;
esac
