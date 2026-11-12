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
mkdir -p "$target"
target="$(cd "$target" && pwd)"
if [ -n "${CLINICPULSE_EXTERNAL_KEY_FILE:-}" ] || { [ -f "$target/.env" ] && \
  grep -Eq '^[[:space:]]*(export[[:space:]]+)?CLINICPULSE_EXTERNAL_KEY_FILE[[:space:]]*=' "$target/.env"; }; then
  echo "External-key installations must be updated with their existing Compose files, not the installer" >&2
  exit 1
fi
mkdir -p "$target/backups"
chmod 700 "$target/backups"

source_compose=""
if [ -f "$0" ]; then
  here="$(cd "$(dirname "$0")" && pwd)"
else
  here=""
fi

if [ -n "$here" ] && [ -f "$here/compose.yaml" ]; then
  command -v cosign >/dev/null 2>&1 || { echo "Cosign is required to verify the ClinicPulse release" >&2; exit 1; }
  cosign verify-blob \
    --bundle "$here/SHA256SUMS.sigstore.json" \
    --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/ClinicPulse/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    "$here/SHA256SUMS" >/dev/null || {
      echo "The release checksum signature is invalid" >&2
      exit 1
    }
  for asset in compose.yaml verify-integrity.sh; do
    expected_checksum="$(awk -v name="$asset" '$2 == name { print $1; count++ } END { if (count != 1) exit 1 }' "$here/SHA256SUMS")" || {
      echo "The signed release checksum for $asset is missing or ambiguous" >&2
      exit 1
    }
    case "$expected_checksum" in
      *[!0-9a-fA-F]*|'') echo "The signed release contains an invalid $asset checksum" >&2; exit 1 ;;
    esac
    [ "${#expected_checksum}" -eq 64 ] || { echo "The signed release contains an invalid $asset checksum" >&2; exit 1; }
    if ! printf '%s  %s\n' "$expected_checksum" "$here/$asset" | sha256sum --check --status -; then
      echo "The downloaded $asset failed checksum verification" >&2
      exit 1
    fi
  done
  if [ "$here" != "$target" ]; then
    cp "$here/compose.yaml" "$target/compose.yaml"
    cp "$here/verify-integrity.sh" "$target/verify-integrity.sh"
    cp "$here/SHA256SUMS" "$target/SHA256SUMS"
    cp "$here/SHA256SUMS.sigstore.json" "$target/SHA256SUMS.sigstore.json"
  fi
elif [ -n "$here" ] && [ -f "$here/../docker/docker-compose.yml" ]; then
  source_compose="$(cd "$here/../docker" && pwd)/docker-compose.yml"
  echo "Using the local source checkout and building its Docker images."
else
  command -v curl >/dev/null 2>&1 || { echo "curl is required to download the ClinicPulse release" >&2; exit 1; }
  command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required to verify the ClinicPulse release" >&2; exit 1; }
  command -v cosign >/dev/null 2>&1 || { echo "Cosign is required to verify the ClinicPulse release" >&2; exit 1; }
  download_dir="$(mktemp -d)"
  trap 'rm -rf "$download_dir"' EXIT HUP INT TERM
  release_url="https://github.com/CyberspaceConsulting/ClinicPulse/releases/latest/download"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/compose.yaml" "$release_url/compose.yaml"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/SHA256SUMS" "$release_url/SHA256SUMS"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/SHA256SUMS.sigstore.json" "$release_url/SHA256SUMS.sigstore.json"
  curl --fail --location --retry 3 --silent --show-error \
    -o "$download_dir/verify-integrity.sh" "$release_url/verify-integrity.sh"
  cosign verify-blob \
    --bundle "$download_dir/SHA256SUMS.sigstore.json" \
    --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/ClinicPulse/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    "$download_dir/SHA256SUMS" >/dev/null || {
      echo "The release checksum signature is invalid" >&2
      exit 1
    }
  for asset in compose.yaml verify-integrity.sh; do
    expected_checksum="$(awk -v name="$asset" '$2 == name { print $1; count++ } END { if (count != 1) exit 1 }' "$download_dir/SHA256SUMS")" || {
      echo "The signed release checksum for $asset is missing or ambiguous" >&2
      exit 1
    }
    case "$expected_checksum" in
      *[!0-9a-fA-F]*|'') echo "The signed release contains an invalid $asset checksum" >&2; exit 1 ;;
    esac
    [ "${#expected_checksum}" -eq 64 ] || { echo "The signed release contains an invalid $asset checksum" >&2; exit 1; }
    if ! printf '%s  %s\n' "$expected_checksum" "$download_dir/$asset" | sha256sum --check --status -; then
      echo "The downloaded $asset failed checksum verification" >&2
      exit 1
    fi
  done
  cp "$download_dir/compose.yaml" "$target/compose.yaml"
  cp "$download_dir/verify-integrity.sh" "$target/verify-integrity.sh"
  cp "$download_dir/SHA256SUMS" "$target/SHA256SUMS"
  cp "$download_dir/SHA256SUMS.sigstore.json" "$target/SHA256SUMS.sigstore.json"
fi

if [ -z "${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-}" ] && [ -f "$target/.env" ] && \
  grep -Eq '^[[:space:]]*(export[[:space:]]+)?CLINICPULSE_DATA_ENCRYPTION_KEY_FILE[[:space:]]*=' "$target/.env"; then
  echo "Set CLINICPULSE_DATA_ENCRYPTION_KEY_FILE in the environment when rerunning the installer with an external key" >&2
  exit 1
fi
if [ -z "${CLINICPULSE_SMTP_PASSWORD_SECRET_FILE:-}" ] && [ -f "$target/.env" ] && \
  grep -Eq '^[[:space:]]*(export[[:space:]]+)?CLINICPULSE_SMTP_PASSWORD_SECRET_FILE[[:space:]]*=' "$target/.env"; then
  echo "Set CLINICPULSE_SMTP_PASSWORD_SECRET_FILE in the environment when rerunning the installer with an external SMTP secret" >&2
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
  legacy_key="$CLINICPULSE_DATA_ENCRYPTION_KEY_FILE"
elif [ -f "$target/secrets/data_encryption_key" ]; then
  legacy_key="$target/secrets/data_encryption_key"
  chmod 700 "$target/secrets"
  chmod 600 "$legacy_key"
else
  legacy_key=""
fi
legacy_smtp="${CLINICPULSE_SMTP_PASSWORD_SECRET_FILE:-$target/secrets/smtp_password}"
case "$legacy_smtp" in
  /*) ;;
  *) legacy_smtp="$target/$legacy_smtp" ;;
esac
if [ -n "${CLINICPULSE_SMTP_PASSWORD_SECRET_FILE:-}" ] && [ ! -f "$legacy_smtp" ]; then
  echo "The configured SMTP password file must already exist" >&2
  exit 1
fi

cd "$target"
compose() {
  if [ -n "$source_compose" ]; then
    docker compose --file "$source_compose" "$@"
  else
    docker compose "$@"
  fi
}

import_secret() {
  compose run --rm --no-deps --volume "$1:/run/clinicpulse-import:ro" --entrypoint /bin/sh backend -c '
    set -eu
    umask 077
    destination="/var/lib/clinicpulse-secrets/$1"
    mkdir -p /var/lib/clinicpulse-secrets
    chmod 700 /var/lib/clinicpulse-secrets
    if [ -e "$destination" ]; then
      cmp -s /run/clinicpulse-import "$destination" || {
        echo "Existing managed secret differs from the original; refusing to overwrite it" >&2
        exit 1
      }
    else
      temporary="$(mktemp /var/lib/clinicpulse-secrets/.import.XXXXXXXX)"
      trap '\''rm -f "$temporary"'\'' EXIT
      cp /run/clinicpulse-import "$temporary"
      if ! ln "$temporary" "$destination"; then
        cmp -s /run/clinicpulse-import "$destination" || exit 1
      fi
    fi
  ' -- "$2"
}

if [ -n "$source_compose" ]; then
  export CLINICPULSE_BACKUP_HOST_DIR="$target/backups"
  (
    if [ -n "${COMPOSE_ENV_FILES:-}" ]; then
      resolved_env_files=""
      saved_ifs="$IFS"
      IFS=,
      set -f
      for env_file in $COMPOSE_ENV_FILES; do
        case "$env_file" in
          /*) ;;
          *) env_file="$target/$env_file" ;;
        esac
        resolved_env_files="${resolved_env_files:+$resolved_env_files,}$env_file"
      done
      IFS="$saved_ifs"
      export COMPOSE_ENV_FILES="$resolved_env_files"
    fi
    cd "$here/.."
    if [ -n "${COMPOSE_ENV_FILES:-}" ]; then
      docker compose --file "$source_compose" build
    elif [ -f "$target/.env" ] && [ "${COMPOSE_DISABLE_ENV_FILE:-0}" != 1 ] && \
      [ "${COMPOSE_DISABLE_ENV_FILE:-false}" != true ]; then
      docker compose --env-file "$target/.env" --file "$source_compose" build
    else
      docker compose --env-file /dev/null --file "$source_compose" build
    fi
  )
else
  sh ./verify-integrity.sh --release-only
  compose pull
fi
if [ -n "$legacy_key" ]; then
  import_secret "$legacy_key" data_encryption_key
  echo "Imported the existing encryption key without deleting the original."
fi
if [ -s "$legacy_smtp" ]; then
  import_secret "$legacy_smtp" smtp_password
  echo "Imported the existing SMTP password without deleting the original."
fi
if [ -n "$source_compose" ]; then
  compose up --no-build -d
else
  compose up -d
  sh ./verify-integrity.sh --check-running
fi
echo "Back up the clinicpulse_keys volume separately from the database; without its key encrypted data is unrecoverable."
echo "ClinicPulse is starting on http://localhost:${CLINICPULSE_PORT:-8080}"
