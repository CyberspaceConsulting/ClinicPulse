import hashlib
import os
from pathlib import Path
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy" / "install.sh"


def installer_environment(tmp_path, *, checksum=None, docker_failure=""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixtures = tmp_path / "release"
    fixtures.mkdir()
    compose = b"services:\n  backend:\n    image: clinicpulse-backend:test\n"
    (fixtures / "compose.yaml").write_bytes(compose)
    digest = checksum or hashlib.sha256(compose).hexdigest()
    (fixtures / "SHA256SUMS").write_text(f"{digest}  compose.yaml\n", encoding="utf-8")

    (bin_dir / "docker").write_text(
        """#!/bin/sh
printf "%s\\n" "$*" >> "$DOCKER_LOG"
[ "$*" != "$DOCKER_FAIL_ON" ] || exit 23
""",
        encoding="utf-8",
    )
    (bin_dir / "curl").write_text(
        """#!/bin/sh
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  */compose.yaml) cp "$RELEASE_FIXTURES/compose.yaml" "$output" ;;
  */SHA256SUMS) cp "$RELEASE_FIXTURES/SHA256SUMS" "$output" ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    (bin_dir / "openssl").write_text(
        '#!/bin/sh\nprintf "test-encryption-key\\n"\n',
        encoding="utf-8",
    )
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)

    environment = os.environ.copy()
    environment.update({
        "PATH": f"{bin_dir}:{environment['PATH']}",
        "DOCKER_LOG": str(tmp_path / "docker.log"),
        "DOCKER_FAIL_ON": docker_failure,
        "RELEASE_FIXTURES": str(fixtures),
    })
    return environment, compose


def run_piped_installer(tmp_path, environment, install_dir):
    return subprocess.run(
        ["sh", "-s", "--", str(install_dir)],
        input=INSTALLER.read_text(encoding="utf-8"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_piped_installer_downloads_verifies_and_starts_release(tmp_path):
    environment, compose = installer_environment(tmp_path)
    install_dir = tmp_path / "installation"

    result = run_piped_installer(tmp_path, environment, install_dir)

    assert result.returncode == 0, result.stderr
    assert (install_dir / "compose.yaml").read_bytes() == compose
    assert not (install_dir / "secrets").exists()
    docker_commands = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    assert "compose pull" in docker_commands
    assert "compose up -d" in docker_commands
    assert "http://localhost:8080" in result.stdout


def test_source_installer_builds_local_compose_without_downloading_release(tmp_path):
    environment, _ = installer_environment(tmp_path)
    repository = tmp_path / "repository"
    deploy_dir = repository / "deploy"
    docker_dir = repository / "docker"
    deploy_dir.mkdir(parents=True)
    docker_dir.mkdir()
    installer = deploy_dir / "install.sh"
    installer.write_text(INSTALLER.read_text(encoding="utf-8"), encoding="utf-8")
    installer.chmod(0o755)
    source_compose = docker_dir / "docker-compose.yml"
    source_compose.write_text("services:\n  web:\n    build: ../frontend\n", encoding="utf-8")
    install_dir = tmp_path / "installation"

    result = subprocess.run(
        ["sh", str(installer), str(install_dir)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Using the local source checkout" in result.stdout
    assert not (install_dir / "secrets").exists()
    docker_commands = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    assert f"compose --file {source_compose} up --build -d" in docker_commands
    assert "compose pull" not in docker_commands
    assert not (install_dir / "compose.yaml").exists()


def test_repeat_install_preserves_key_and_existing_backups(tmp_path):
    environment, _ = installer_environment(tmp_path)
    install_dir = tmp_path / "installation"
    first = run_piped_installer(tmp_path, environment, install_dir)
    assert first.returncode == 0, first.stderr

    key_path = install_dir / "secrets" / "data_encryption_key"
    key_path.parent.mkdir()
    key_path.write_text("existing-production-key\n", encoding="utf-8")
    backup_path = install_dir / "backups" / "previous-backup"
    backup_path.write_text("existing backup", encoding="utf-8")

    second = run_piped_installer(tmp_path, environment, install_dir)

    assert second.returncode == 0, second.stderr
    assert key_path.read_text(encoding="utf-8") == "existing-production-key\n"
    assert backup_path.read_text(encoding="utf-8") == "existing backup"
    assert "Imported the existing encryption key" in second.stdout
    assert f"--volume {key_path}:/run/clinicpulse-import:ro" in (tmp_path / "docker.log").read_text(encoding="utf-8")


def test_installer_uses_external_key_and_does_not_create_a_replacement(tmp_path):
    environment, _ = installer_environment(tmp_path)
    key = tmp_path / "external-key"
    key.write_text("existing-key\n", encoding="utf-8")
    environment["CLINICPULSE_DATA_ENCRYPTION_KEY_FILE"] = str(key)
    install_dir = tmp_path / "installation"

    result = run_piped_installer(tmp_path, environment, install_dir)

    assert result.returncode == 0, result.stderr
    assert key.read_text(encoding="utf-8") == "existing-key\n"
    assert not (install_dir / "secrets" / "data_encryption_key").exists()
    assert f"--volume {key}:/run/clinicpulse-import:ro" in (tmp_path / "docker.log").read_text(encoding="utf-8")


def test_installer_rejects_missing_external_key(tmp_path):
    environment, _ = installer_environment(tmp_path)
    environment["CLINICPULSE_DATA_ENCRYPTION_KEY_FILE"] = str(tmp_path / "missing-key")
    result = run_piped_installer(tmp_path, environment, tmp_path / "installation")
    assert result.returncode != 0
    assert "must already exist" in result.stderr
    assert (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines() == ["compose version"]


def test_installer_rejects_missing_external_smtp_password(tmp_path):
    environment, _ = installer_environment(tmp_path)
    environment["CLINICPULSE_SMTP_PASSWORD_SECRET_FILE"] = str(tmp_path / "missing-smtp")
    result = run_piped_installer(tmp_path, environment, tmp_path / "installation")
    assert result.returncode != 0
    assert "SMTP password file must already exist" in result.stderr


@pytest.mark.parametrize("configured_in_dotenv", [False, True])
def test_installer_refuses_external_key_mode(tmp_path, configured_in_dotenv):
    environment, _ = installer_environment(tmp_path)
    install_dir = tmp_path / "installation"
    if configured_in_dotenv:
        environment.pop("CLINICPULSE_EXTERNAL_KEY_FILE", None)
        install_dir.mkdir()
        (install_dir / ".env").write_text("CLINICPULSE_EXTERNAL_KEY_FILE=/secure/key\n", encoding="utf-8")
    else:
        environment["CLINICPULSE_EXTERNAL_KEY_FILE"] = "/secure/key"
    result = run_piped_installer(tmp_path, environment, install_dir)
    assert result.returncode != 0
    assert "must be updated with their existing Compose files" in result.stderr
    assert (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines() == ["compose version"]


def test_installer_requires_external_smtp_environment_when_configured_in_dotenv(tmp_path):
    environment, _ = installer_environment(tmp_path)
    environment.pop("CLINICPULSE_SMTP_PASSWORD_SECRET_FILE", None)
    install_dir = tmp_path / "installation"
    install_dir.mkdir()
    (install_dir / ".env").write_text("CLINICPULSE_SMTP_PASSWORD_SECRET_FILE=/secure/smtp\n", encoding="utf-8")
    result = run_piped_installer(tmp_path, environment, install_dir)
    assert result.returncode != 0
    assert "in the environment" in result.stderr


def test_installer_requires_external_key_environment_when_configured_in_dotenv(tmp_path):
    environment, _ = installer_environment(tmp_path)
    environment.pop("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", None)
    install_dir = tmp_path / "installation"
    install_dir.mkdir()
    (install_dir / ".env").write_text("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE=/secure/key\n", encoding="utf-8")
    result = run_piped_installer(tmp_path, environment, install_dir)
    assert result.returncode != 0
    assert "in the environment" in result.stderr
    assert not (install_dir / "secrets" / "data_encryption_key").exists()


def test_installer_restricts_existing_key_permissions(tmp_path):
    environment, _ = installer_environment(tmp_path)
    install_dir = tmp_path / "installation"
    key = install_dir / "secrets" / "data_encryption_key"
    key.parent.mkdir(parents=True)
    key.write_text("existing-key\n", encoding="utf-8")
    key.chmod(0o644)
    result = run_piped_installer(tmp_path, environment, install_dir)
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(key.stat().st_mode) == 0o600


def test_bad_compose_checksum_stops_before_creating_key_or_starting_containers(tmp_path):
    environment, _ = installer_environment(tmp_path, checksum="0" * 64)
    install_dir = tmp_path / "installation"

    result = run_piped_installer(tmp_path, environment, install_dir)

    assert result.returncode != 0
    assert "checksum verification" in result.stderr
    assert not (install_dir / "secrets" / "data_encryption_key").exists()
    assert (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines() == ["compose version"]


def test_docker_start_failure_is_reported_without_success_message(tmp_path):
    environment, _ = installer_environment(tmp_path, docker_failure="compose up -d")
    install_dir = tmp_path / "installation"

    result = run_piped_installer(tmp_path, environment, install_dir)

    assert result.returncode == 23
    assert "ClinicPulse is starting" not in result.stdout
    assert not (install_dir / "secrets").exists()
    assert (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()[-1] == "compose up -d"
