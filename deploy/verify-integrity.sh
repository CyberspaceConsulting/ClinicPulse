#!/bin/sh
set -eu

mode=--check-running
release_dir=.
project_dir="$PWD"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --release-only|--check-running) mode="$1"; shift ;;
    --release-dir)
      [ "$#" -ge 2 ] || { echo "--release-dir requires a directory" >&2; exit 2; }
      release_dir="$2"
      shift 2
      ;;
    --project-dir)
      [ "$#" -ge 2 ] || { echo "--project-dir requires a directory" >&2; exit 2; }
      project_dir="$2"
      shift 2
      ;;
    *) echo "Usage: sh verify-integrity.sh [--release-only|--check-running] [--release-dir DIR] [--project-dir DIR]" >&2; exit 2 ;;
  esac
done
release_dir="$(cd "$release_dir" && pwd)"
project_dir="$(cd "$project_dir" && pwd)"
script_path="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

command -v docker >/dev/null 2>&1 || { echo "Docker is required" >&2; exit 1; }
command -v cosign >/dev/null 2>&1 || { echo "Cosign is required to verify the Medora release" >&2; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required" >&2; exit 1; }

cosign verify-blob \
  --bundle "$release_dir/SHA256SUMS.sigstore.json" \
  --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/Medora/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "$release_dir/SHA256SUMS" >/dev/null || {
    echo "The release checksum signature is invalid" >&2
    exit 1
  }

verify_asset() {
  asset="$1"
  path="$2"
  expected_checksum="$(awk -v name="$asset" '$2 == name { print $1; count++ } END { if (count != 1) exit 1 }' "$release_dir/SHA256SUMS")" || {
    echo "The signed release checksum for $asset is missing or ambiguous" >&2
    exit 1
  }
  case "$expected_checksum" in
    *[!0-9a-fA-F]*|'') echo "The signed release contains an invalid $asset checksum" >&2; exit 1 ;;
  esac
  [ "${#expected_checksum}" -eq 64 ] || { echo "The signed release contains an invalid $asset checksum" >&2; exit 1; }
  if ! printf '%s  %s\n' "$expected_checksum" "$path" | sha256sum --check --status -; then
    echo "The release asset $asset failed checksum verification" >&2
    exit 1
  fi
}

verify_asset compose.yaml "$release_dir/compose.yaml"
verify_asset verify-integrity.sh "$script_path"

compose() {
  docker compose --project-directory "$project_dir" -f "$release_dir/compose.yaml" "$@"
}

images="$(compose config --images)"
backend_image=""
web_image=""
for image in $images; do
  case "$image" in
    ghcr.io/cyberspaceconsulting/medora-backend*@sha256:*)
      [ -z "$backend_image" ] || { echo "The release contains multiple backend images" >&2; exit 1; }
      backend_image="$image"
      ;;
    ghcr.io/cyberspaceconsulting/medora-web*@sha256:*)
      [ -z "$web_image" ] || { echo "The release contains multiple web images" >&2; exit 1; }
      web_image="$image"
      ;;
  esac
done

for image in "$backend_image" "$web_image"; do
  [ -n "$image" ] || { echo "The signed Compose file must pin both Medora images by digest" >&2; exit 1; }
  digest="${image##*@sha256:}"
  case "$digest" in
    *[!0-9a-fA-F]*|'') echo "The release contains an invalid image digest" >&2; exit 1 ;;
  esac
  [ "${#digest}" -eq 64 ] || { echo "The release contains an invalid image digest" >&2; exit 1; }
done

if [ "$mode" = "--release-only" ]; then
  echo "Release signature, checksums, and pinned image digests are valid."
  exit 0
fi

for service in backend web; do
  container_id="$(compose ps -q "$service")"
  [ -n "$container_id" ] || { echo "The $service container is not running" >&2; exit 1; }
  running_ref="$(docker inspect --format '{{.Config.Image}}' "$container_id")"
  running_id="$(docker inspect --format '{{.Image}}' "$container_id")"
  case "$service:$running_ref" in
    backend:ghcr.io/cyberspaceconsulting/medora-backend*@sha256:*) ;;
    web:ghcr.io/cyberspaceconsulting/medora-web*@sha256:*) ;;
    *) echo "The running $service container does not use a digest-pinned official image" >&2; exit 1 ;;
  esac
  image_found=false
  for image in $images; do
    if [ "$image" = "$running_ref" ]; then
      image_found=true
      break
    fi
  done
  [ "$image_found" = true ] || { echo "The running $service image differs from the signed Compose release" >&2; exit 1; }
  expected_id="$(docker image inspect "$running_ref" --format '{{.Id}}')"
  [ "$expected_id" = "$running_id" ] || {
    echo "The running $service container does not match its local image reference" >&2
    exit 1
  }
done

echo "The running backend and web containers match the signed release image digests."