import hashlib
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "deploy" / "install.sh"


def test_piped_installer_downloads_verifies_and_starts_release(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixtures = tmp_path / "release"
    fixtures.mkdir()
    compose = b"services:\n  backend:\n    image: clinicpulse-backend:test\n"
    (fixtures / "compose.yaml").write_bytes(compose)
    checksum = hashlib.sha256(compose).hexdigest()
    (fixtures / "SHA256SUMS").write_text(f"{checksum}  compose.yaml\n", encoding="utf-8")

    (bin_dir / "docker").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\n',
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

    install_dir = tmp_path / "installation"
    environment = os.environ.copy()
    environment.update({
        "PATH": f"{bin_dir}:{environment['PATH']}",
        "DOCKER_LOG": str(tmp_path / "docker.log"),
        "RELEASE_FIXTURES": str(fixtures),
    })
    result = subprocess.run(
        ["sh", "-s", "--", str(install_dir)],
        input=INSTALLER.read_text(encoding="utf-8"),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert (install_dir / "compose.yaml").read_bytes() == compose
    assert (install_dir / "secrets" / "data_encryption_key").read_text(encoding="utf-8") == "test-encryption-key\n"
    docker_commands = (tmp_path / "docker.log").read_text(encoding="utf-8").splitlines()
    assert "compose pull" in docker_commands
    assert "compose up -d" in docker_commands
    assert f"http://localhost:8080" in result.stdout
