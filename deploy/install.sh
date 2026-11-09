#!/bin/sh
# ClinicPulse release installer. Usage: ./install.sh [install-directory]
# Run it from a downloaded, selected release; it never overwrites an existing key or volume.
set -eu

target="${1:-clinicpulse}"
here="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f "$here/compose.yaml" ]; then
  echo "compose.yaml from the same release must be next to install.sh" >&2
  exit 1
fi
command -v docker >/dev/null 2>&1 || { echo "Docker is required" >&2; exit 1; }
# The release images are multi-arch (amd64 + arm64); Docker pulls the matching variant itself.
case "$(uname -m)" in
  x86_64|amd64|aarch64|arm64) ;;
  *) echo "Unsupported CPU architecture $(uname -m): ClinicPulse needs 64-bit x86 or ARM (e.g. Raspberry Pi 4/5 with a 64-bit OS)" >&2; exit 1 ;;
esac
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required" >&2; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "openssl is required to create the encryption key" >&2; exit 1; }

mkdir -p "$target/secrets"
chmod 700 "$target/secrets"
mkdir -p "$target/backups"
chmod 700 "$target/backups"
if [ "$here" != "$(cd "$target" && pwd)" ]; then
  cp "$here/compose.yaml" "$target/compose.yaml"
fi

if [ ! -f "$target/secrets/data_encryption_key" ]; then
  (umask 077 && openssl rand -base64 48 > "$target/secrets/data_encryption_key")
  echo "Created $target/secrets/data_encryption_key. Back it up separately from the database; without it encrypted data is unrecoverable."
else
  echo "Keeping existing encryption key."
fi
if [ ! -f "$target/secrets/smtp_password" ]; then
  (umask 077 && : > "$target/secrets/smtp_password")
fi
chmod 600 "$target/secrets/smtp_password"

cd "$target"
docker compose pull
docker compose up -d
echo "ClinicPulse is starting on http://localhost:${CLINICPULSE_PORT:-8080}"
