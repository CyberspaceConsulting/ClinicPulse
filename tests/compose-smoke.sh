#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
temporary_directory="$(mktemp -d)"
project="clinicpulse-smoke-${GITHUB_RUN_ID:-local}-$$"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

mkdir -p "$temporary_directory/backups"
openssl rand -base64 48 > "$temporary_directory/data_encryption_key"
: > "$temporary_directory/smtp_password"

export CLINICPULSE_PORT="$port"
export CLINICPULSE_DATA_ENCRYPTION_KEY_FILE="$temporary_directory/data_encryption_key"
export CLINICPULSE_SMTP_PASSWORD_SECRET_FILE="$temporary_directory/smtp_password"
export CLINICPULSE_BACKUP_HOST_DIR="$temporary_directory/backups"
export CLINICPULSE_VERSION="compose-smoke"

compose() {
  docker compose --project-name "$project" --file "$root/docker/docker-compose.yml" "$@"
}

cleanup() {
  result=$?
  if [ "$result" -ne 0 ]; then
    compose logs || true
  fi
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$temporary_directory"
  exit "$result"
}
trap cleanup EXIT

compose up --build --detach

database_container="$(compose ps --quiet db)"
attempt=0
while [ "$attempt" -lt 60 ]; do
  database_health="$(docker inspect --format '{{.State.Health.Status}}' "$database_container" 2>/dev/null || true)"
  [ "$database_health" = "healthy" ] && break
  attempt=$((attempt + 1))
  sleep 2
done
[ "$database_health" = "healthy" ] || {
  echo "PostgreSQL did not become healthy" >&2
  exit 1
}

attempt=0
while [ "$attempt" -lt 60 ]; do
  if curl --fail --silent --show-error "http://127.0.0.1:$port/api/health" \
    --output "$temporary_directory/health.json" 2>/dev/null; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done
python3 - "$temporary_directory/health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as response:
    health = json.load(response)
if health.get("status") != "ok":
    raise SystemExit(f"Unexpected API health response: {health!r}")
PY

curl --fail --silent --show-error "http://127.0.0.1:$port/" \
  --output "$temporary_directory/index.html"
grep -qi "ClinicPulse" "$temporary_directory/index.html"
backend_container="$(compose ps --quiet backend)"
[ -n "$backend_container" ]
[ "$(docker inspect --format '{{.State.Status}}' "$backend_container")" = "running" ]

echo "Compose smoke test passed: web, backend, and healthy PostgreSQL are running; API is reachable through nginx."
