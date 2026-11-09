import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "compose.encrypted.yaml"


@pytest.mark.parametrize("base", [ROOT / "docker-compose.yml", ROOT / "deploy" / "compose.release.yaml"])
def test_encrypted_storage_overlay_keeps_database_mount_explicit(base, tmp_path):
    if shutil.which("docker"):
        compose = ["docker", "compose"]
    elif shutil.which("docker-compose"):
        compose = ["docker-compose"]
    else:
        if os.environ.get("CI"):
            pytest.fail("Docker is required to validate Compose configuration in CI")
        pytest.skip("Docker Compose is not available locally")
    environment = os.environ.copy()
    environment["CLINICPULSE_ENCRYPTED_PGDATA"] = str(tmp_path)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    command = compose + [
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
