import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "docker" / "compose.encrypted.yaml"
EXTERNAL_KEY_OVERLAY = ROOT / "docker" / "compose.external-key.yaml"
GHCR_SOURCE_LABEL = 'LABEL org.opencontainers.image.source="https://github.com/CyberspaceConsulting/ClinicPulse"'


def compose_command():
    if shutil.which("docker"):
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    if os.environ.get("CI"):
        pytest.fail("Docker is required to validate Compose configuration in CI")
    pytest.skip("Docker Compose is not available locally")


def test_source_compose_keeps_existing_project_and_storage_paths(tmp_path):
    environment = os.environ.copy()
    for name in ("COMPOSE_PROJECT_NAME", "CLINICPULSE_BACKUP_HOST_DIR", "CLINICPULSE_DATA_ENCRYPTION_KEY_FILE"):
        environment.pop(name, None)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = compose_command() + [
        "--env-file", str(env_file), "-f", str(ROOT / "docker" / "docker-compose.yml"),
        "config", "--format", "json",
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    config = json.loads(result.stdout)
    assert config["name"] == "clinicpulse"
    assert config["services"]["backend"]["build"]["context"] == str(ROOT / "backend")
    assert config["services"]["web"]["build"]["context"] == str(ROOT / "frontend")
    assert config["services"]["backend"]["volumes"][0]["source"] == str(ROOT / "backups")
    assert config["services"]["backend"]["volumes"][1]["source"] == "clinicpulse_keys"
    assert config["services"]["backend"]["volumes"][1]["target"] == "/var/lib/clinicpulse-secrets"
    assert "secrets" not in config


def test_release_compose_manages_keys_in_a_separate_volume(tmp_path):
    environment = os.environ.copy()
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = compose_command() + [
        "--env-file", str(env_file), "-f", str(ROOT / "docker" / "compose.release.yaml"),
        "config", "--format", "json",
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    config = json.loads(result.stdout)
    backend = config["services"]["backend"]
    assert backend["environment"]["CLINICPULSE_MANAGED_KEY_FILE"] == "/var/lib/clinicpulse-secrets/data_encryption_key"
    assert any(volume["source"] == "clinicpulse_keys" for volume in backend["volumes"])
    assert "secrets" not in config


@pytest.mark.parametrize("base", [ROOT / "docker" / "docker-compose.yml", ROOT / "docker" / "compose.release.yaml"])
def test_external_key_overlay_uses_read_only_existing_file(base, tmp_path):
    environment = os.environ.copy()
    key_path = tmp_path / "key"
    key_path.write_text("key", encoding="ascii")
    environment["CLINICPULSE_EXTERNAL_KEY_FILE"] = str(key_path)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = compose_command() + [
        "--env-file", str(env_file), "-f", str(base), "-f", str(EXTERNAL_KEY_OVERLAY),
        "config", "--format", "json",
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    services = json.loads(result.stdout)["services"]
    backend = services["backend"]
    assert backend["environment"]["CLINICPULSE_DATA_ENCRYPTION_KEY_FILE"] == "/run/clinicpulse-external/data_encryption_key"
    mount = next(volume for volume in backend["volumes"] if volume["target"] == "/run/clinicpulse-external/data_encryption_key")
    assert mount["source"] == str(key_path)
    assert mount["read_only"] is True
    assert mount.get("bind", {}).get("create_host_path", False) is False
    assert backend["restart"] == "no"
    assert services["web"]["restart"] == "no"
    environment.pop("CLINICPULSE_EXTERNAL_KEY_FILE")
    assert subprocess.run(command, env=environment, capture_output=True, text=True).returncode != 0


@pytest.mark.parametrize("dockerfile", [ROOT / "docker" / "api.Dockerfile", ROOT / "docker" / "web.Dockerfile"])
def test_release_images_identify_repository_for_ghcr_access(dockerfile):
    assert GHCR_SOURCE_LABEL in dockerfile.read_text(encoding="utf-8")


def test_release_image_version_is_built_from_the_actual_tag():
    workflow = (ROOT / ".github" / "workflows" / "release-images.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker" / "compose.release.yaml").read_text(encoding="utf-8")
    assert "CLINICPULSE_IMAGE_VERSION=${{ env.IMAGE_TAG }}" in workflow
    assert "CLINICPULSE_IMAGE_VERSION=${CLINICPULSE_IMAGE_VERSION}" in dockerfile
    assert "clinicpulse-backend:__IMAGE_TAG__" in compose
    assert "CLINICPULSE_VERSION:" not in compose


def test_release_publishes_external_key_overlay_with_checksum():
    workflow = (ROOT / ".github" / "workflows" / "release-images.yml").read_text(encoding="utf-8")
    assert "cp docker/compose.external-key.yaml dist/compose.external-key.yaml" in workflow
    assert "sha256sum compose.yaml compose.encrypted.yaml compose.external-key.yaml" in workflow
    assert "gh release upload" in workflow and "dist/compose.external-key.yaml" in workflow


@pytest.mark.parametrize("base", [ROOT / "docker" / "docker-compose.yml", ROOT / "docker" / "compose.release.yaml"])
def test_encrypted_storage_overlay_keeps_database_mount_explicit(base, tmp_path):
    environment = os.environ.copy()
    environment["CLINICPULSE_ENCRYPTED_PGDATA"] = str(tmp_path)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = compose_command() + [
        "--env-file", str(env_file), "-f", str(base), "-f", str(OVERLAY),
        "config", "--format", "json",
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    config = json.loads(result.stdout)
    services = config["services"]
    mounts = [volume for volume in services["db"]["volumes"] if volume["target"] == "/var/lib/postgresql"]
    assert len(mounts) == 1
    assert mounts[0]["type"] == "bind"
    assert mounts[0]["source"] == str(tmp_path)
    assert mounts[0].get("bind", {}).get("create_host_path", False) is False
    assert all(services[name]["restart"] == "no" for name in ("db", "backend", "web"))

    environment.pop("CLINICPULSE_ENCRYPTED_PGDATA")
    missing = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert missing.returncode != 0
    assert "CLINICPULSE_ENCRYPTED_PGDATA" in missing.stderr
