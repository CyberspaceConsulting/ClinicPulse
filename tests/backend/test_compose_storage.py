import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "docker" / "compose.encrypted.yaml"
GHCR_SOURCE_LABEL = 'LABEL org.opencontainers.image.source="https://github.com/the1andoni/ClinicPulse"'


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
    assert config["services"]["api"]["build"]["context"] == str(ROOT / "backend")
    assert config["services"]["web"]["build"]["context"] == str(ROOT / "frontend")
    assert config["services"]["api"]["volumes"][0]["source"] == str(ROOT / "backups")
    assert config["secrets"]["clinicpulse_data_encryption_key"]["file"] == str(ROOT / "secrets" / "data_encryption_key")
    assert config["secrets"]["smtp_password"]["file"] == str(ROOT / "secrets" / "smtp_password")


@pytest.mark.parametrize("dockerfile", [ROOT / "docker" / "api.Dockerfile", ROOT / "docker" / "web.Dockerfile"])
def test_release_images_identify_repository_for_ghcr_access(dockerfile):
    assert GHCR_SOURCE_LABEL in dockerfile.read_text(encoding="utf-8")


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
    mounts = [volume for volume in services["db"]["volumes"] if volume["target"] == "/var/lib/postgresql/data"]
    assert len(mounts) == 1
    assert mounts[0]["type"] == "bind"
    assert mounts[0]["source"] == str(tmp_path)
    assert mounts[0].get("bind", {}).get("create_host_path", False) is False
    assert all(services[name]["restart"] == "no" for name in ("db", "api", "web"))

    environment.pop("CLINICPULSE_ENCRYPTED_PGDATA")
    missing = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert missing.returncode != 0
    assert "CLINICPULSE_ENCRYPTED_PGDATA" in missing.stderr
