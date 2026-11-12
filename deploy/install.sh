#!/bin/sh
# ClinicPulse installer. Usage: ./install.sh [install-directory]
set -eu

target="${1:-clinicpulse}"
command -v docker >/dev/null 2>&1 || { echo "Docker is required" >&2; exit 1; }
# The release images are multi-arch (amd64 + arm64); Docker pulls the matching variant itself.
case "$(uname -m)" in
  x86_64|amd64|aarch64|arm64) ;;
  *) echo "Unsupported CPU architecture $(uname -m): ClinicPulse needs 64-bit x86 or ARM (e.g. Raspberry Pi 4/5 with a 64-bit OS)" >&2; exit 1 ;;
esac
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "openssl is required to create the encryption key" >&2; exit 1; }

mkdir -p "$target"
target="$(cd "$target" && pwd)"
mkdir -p "$target/secrets"
chmod 700 "$target/secrets"
mkdir -p "$target/backups"
chmod 700 "$target/backups"

source_compose=""
if [ -f "$0" ]; then
  here="$(cd "$(dirname "$0")" && pwd)"
else
  here=""
fi

if [ -n "$here" ] && [ -f "$here/compose.yaml" ]; then
  if [ "$here" != "$target" ]; then
    cp "$here/compose.yaml" "$target/compose.yaml"
  fi
elif [ -n "$here" ] && [ -f "$here/../docker/docker-compose.yml" ]; then
  source_compose="$(cd "$here/../docker" && pwd)/docker-compose.yml"
  echo "Using the local source checkout and building its Docker images."
else
  command -v curl >/dev/null 2>&1 || { echo "curl is required to download the ClinicPulse release" >&2; exit 1; }
  command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required to verify the ClinicPulse release" >&2; exit 1; }
  download_dir="$(mktemp -d)"
  trap 'rm -rf "$download_dir"' EXIT HUP INT TERM
  release_url="https://github.com/CyberspaceConsulting/ClinicPulse/releases/latest/download"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/compose.yaml" "$release_url/compose.yaml"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/SHA256SUMS" "$release_url/SHA256SUMS"
  expected_checksum="$(awk '$2 == "compose.yaml" { print $1; count++ } END { if (count != 1) exit 1 }' "$download_dir/SHA256SUMS")" || {
    echo "The release checksum for compose.yaml is missing or ambiguous" >&2
    exit 1
  }
  case "$expected_checksum" in
    *[!0-9a-fA-F]*|'') echo "The release contains an invalid compose.yaml checksum" >&2; exit 1 ;;
  esac
  [ "${#expected_checksum}" -eq 64 ] || { echo "The release contains an invalid compose.yaml checksum" >&2; exit 1; }
  if ! printf '%s  %s\n' "$expected_checksum" "$download_dir/compose.yaml" | sha256sum --check --status -; then
    echo "The downloaded compose.yaml failed checksum verification" >&2
    exit 1
  fi
  cp "$download_dir/compose.yaml" "$target/compose.yaml"
fi

if [ -z "${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-}" ] && [ -f "$target/.env" ] && \
  grep -Eq '^[[:space:]]*(export[[:space:]]+)?CLINICPULSE_DATA_ENCRYPTION_KEY_FILE[[:space:]]*=' "$target/.env"; then
  echo "Set CLINICPULSE_DATA_ENCRYPTION_KEY_FILE in the environment when rerunning the installer with an external key" >&2
  exit 1
fi
if [ -n "${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-}" ]; then
  case "$CLINICPULSE_DATA_ENCRYPTION_KEY_FILE" in
    /*) ;;
    *) echo "CLINICPULSE_DATA_ENCRYPTION_KEY_FILE must be an absolute path" >&2; exit 1 ;;
  esac
  [ -f "$CLINICPULSE_DATA_ENCRYPTION_KEY_FILE" ] && [ -r "$CLINICPULSE_DATA_ENCRYPTION_KEY_FILE" ] || {
    echo "The configured encryption key file must already exist and be readable" >&2; exit 1
  }
  echo "Using the configured encryption key file."
elif [ ! -f "$target/secrets/data_encryption_key" ]; then
  (umask 077 && openssl rand -base64 48 > "$target/secrets/data_encryption_key")
  echo "Created $target/secrets/data_encryption_key. Back it up separately from the database; without it encrypted data is unrecoverable."
else
  echo "Keeping existing encryption key."
fi
if [ -z "${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-}" ]; then
  chmod 600 "$target/secrets/data_encryption_key"
fi
if [ ! -f "$target/secrets/smtp_password" ]; then
  (umask 077 && : > "$target/secrets/smtp_password")
fi
chmod 600 "$target/secrets/smtp_password"

cd "$target"
if [ -n "$source_compose" ]; then
  export CLINICPULSE_DATA_ENCRYPTION_KEY_FILE="${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-$target/secrets/data_encryption_key}"
  export CLINICPULSE_SMTP_PASSWORD_SECRET_FILE="$target/secrets/smtp_password"
  export CLINICPULSE_BACKUP_HOST_DIR="$target/backups"
  docker compose --file "$source_compose" up --build -d
else
  docker compose pull
  docker compose up -d
fi
echo "ClinicPulse is starting on http://localhost:${CLINICPULSE_PORT:-8080}"
