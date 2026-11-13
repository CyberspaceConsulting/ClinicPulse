#!/bin/sh
set -eu

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
temporary_directory="$(mktemp -d)"
project="medora-smoke-${GITHUB_RUN_ID:-local}-$$"
port="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

mkdir -p "$temporary_directory/backups"

export MEDORA_PORT="$port"
export MEDORA_BACKUP_HOST_DIR="$temporary_directory/backups"
export MEDORA_VERSION="compose-smoke"

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
grep -qi "Medora" "$temporary_directory/index.html"
not_found_status="$(curl --silent --show-error --output "$temporary_directory/not-found.html" \
  --write-out '%{http_code}' "http://127.0.0.1:$port/does-not-exist")"
[ "$not_found_status" = "404" ]
grep -qi "Medora" "$temporary_directory/not-found.html"
backend_container="$(compose ps --quiet backend)"
[ -n "$backend_container" ]
[ "$(docker inspect --format '{{.State.Status}}' "$backend_container")" = "running" ]

compose exec -T db pg_dump -Fc -U medora -d medora > "$temporary_directory/database.dump"
compose exec -T db pg_restore --list < "$temporary_directory/database.dump" > /dev/null
compose exec -T db createdb -U medora medora_restore_test
compose exec -T db pg_restore --exit-on-error --no-owner --no-acl -U medora \
  -d medora_restore_test < "$temporary_directory/database.dump"
restored_tables="$(compose exec -T db psql -U medora -d medora_restore_test -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
[ "$restored_tables" -gt 0 ]

key_digest="$(compose exec -T backend sha256sum /var/lib/medora-secrets/data_encryption_key)"
compose exec -T backend python -c 'from pathlib import Path; from app.managed_secrets import export_secrets; Path("/backups/secret-test.cpkeys").write_bytes(export_secrets(Path("/var/lib/medora-secrets"), "test-only-passphrase"))'
compose restart backend
curl --retry 10 --retry-all-errors --fail --silent --show-error \
  "http://127.0.0.1:$port/api/health" --output /dev/null
[ "$(compose exec -T backend sha256sum /var/lib/medora-secrets/data_encryption_key)" = "$key_digest" ]

compose stop backend
compose run --rm --no-deps --entrypoint /bin/sh backend -c \
  'rm /var/lib/medora-secrets/data_encryption_key'
if compose run --rm --no-deps backend > "$temporary_directory/missing-key.log" 2>&1; then
  echo "Backend unexpectedly started with an existing database and missing key" >&2
  exit 1
fi
grep -q "Managed encryption key is missing for an existing database" "$temporary_directory/missing-key.log"
compose run --rm --no-deps --entrypoint python backend -c \
  'from pathlib import Path; from app.managed_secrets import restore_secrets; restore_secrets(Path("/var/lib/medora-secrets"), Path("/backups/secret-test.cpkeys").read_bytes(), "test-only-passphrase")'
[ "$(compose run --rm --no-deps --entrypoint sha256sum backend /var/lib/medora-secrets/data_encryption_key)" = "$key_digest" ]
compose start backend
curl --retry 10 --retry-all-errors --fail --silent --show-error \
  "http://127.0.0.1:$port/api/health" --output /dev/null

compose down --volumes --remove-orphans
project="${project}-import"
legacy_directory="$temporary_directory/legacy"
mkdir -p "$legacy_directory/secrets"
openssl rand -base64 48 > "$legacy_directory/secrets/data_encryption_key"
printf '%s\n' 'test-smtp-password' > "$legacy_directory/secrets/smtp_password"
COMPOSE_PROJECT_NAME="$project" sh "$root/deploy/install.sh" "$legacy_directory"
curl --retry 10 --retry-all-errors --fail --silent --show-error \
  "http://127.0.0.1:$port/api/health" --output /dev/null
compose run --rm --no-deps --volume "$legacy_directory/secrets:/run/legacy:ro" --entrypoint /bin/sh backend -c \
  'cmp -s /run/legacy/data_encryption_key /var/lib/medora-secrets/data_encryption_key && cmp -s /run/legacy/smtp_password /var/lib/medora-secrets/smtp_password'

external_directory="$temporary_directory/external"
recovery_directory="$temporary_directory/external-recovery"
mkdir -m 700 "$external_directory" "$recovery_directory"
cp "$legacy_directory/secrets/data_encryption_key" "$external_directory/data_encryption_key"
chmod 600 "$external_directory/data_encryption_key"
export MEDORA_EXTERNAL_KEY_FILE="$external_directory/data_encryption_key"
external_compose() {
  docker compose --project-name "$project" --file "$root/docker/docker-compose.yml" \
    --file "$root/docker/compose.external-key.yaml" "$@"
}
external_compose up -d --no-deps --force-recreate backend web
curl --retry 10 --retry-all-errors --fail --silent --show-error \
  "http://127.0.0.1:$port/api/health" --output /dev/null
if external_compose exec -T backend touch /run/medora-external/data_encryption_key 2>/dev/null; then
  echo "External key mount unexpectedly allowed writing" >&2
  exit 1
fi
external_compose run --rm --no-deps --entrypoint python backend -c \
  'import getpass, sys; from app.managed_secrets import main; getpass.getpass = lambda prompt: "test-only-passphrase"; sys.argv = ["managed_secrets", "export", "/backups/external-test.cpkeys"]; sys.exit(main())'
external_compose run --rm --no-deps --volume "$recovery_directory:/run/key-recovery" --entrypoint python backend -c \
  'import getpass, sys; from app.managed_secrets import main; getpass.getpass = lambda prompt: "test-only-passphrase"; sys.argv = ["managed_secrets", "import", "/backups/external-test.cpkeys", "--key-directory", "/run/key-recovery"]; sys.exit(main())'
external_compose run --rm --no-deps --volume "$recovery_directory:/run/key-recovery:ro" --entrypoint /bin/sh backend -c \
  'cmp -s /run/medora-external/data_encryption_key /run/key-recovery/data_encryption_key'
mv "$external_directory/data_encryption_key" "$external_directory/unmounted-key"
if external_compose run --rm --no-deps --entrypoint true backend > "$temporary_directory/missing-external-key.log" 2>&1; then
  echo "External key mount unexpectedly succeeded when the key was missing" >&2
  exit 1
fi
mv "$external_directory/unmounted-key" "$external_directory/data_encryption_key"
unset MEDORA_EXTERNAL_KEY_FILE

printf '%s\n' 'different-key' > "$legacy_directory/secrets/data_encryption_key"
if COMPOSE_PROJECT_NAME="$project" sh "$root/deploy/install.sh" "$legacy_directory" > "$temporary_directory/conflicting-key.log" 2>&1; then
  echo "Installer unexpectedly accepted a conflicting encryption key" >&2
  exit 1
fi
grep -q "refusing to overwrite" "$temporary_directory/conflicting-key.log"

echo "Compose smoke test passed: web, backend, and healthy PostgreSQL are running; API is reachable through nginx."
