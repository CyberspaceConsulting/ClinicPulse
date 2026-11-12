import base64

import pytest

from app.managed_secrets import export_secrets, main, restore_secrets


def test_secret_backup_is_encrypted_and_restores_without_overwriting(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    key = base64.b64encode(b"x" * 48).decode("ascii") + "\n"
    (source / "data_encryption_key").write_text(key, encoding="ascii")
    (source / "smtp_password").write_text("smtp-password", encoding="utf-8")
    data = export_secrets(source, "long backup passphrase")
    assert key.encode() not in data
    assert b"smtp-password" not in data
    target = tmp_path / "target"
    with pytest.raises(ValueError, match="Incorrect password"):
        restore_secrets(target, data, "incorrect passphrase")
    assert not target.exists()
    restore_secrets(target, data, "long backup passphrase")
    assert (target / "data_encryption_key").read_text(encoding="ascii") == key
    assert (target / "smtp_password").read_text(encoding="utf-8") == "smtp-password"
    assert (target / "data_encryption_key").stat().st_mode & 0o777 == 0o600
    restore_secrets(target, data, "long backup passphrase")
    (target / "smtp_password").write_text("different", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        restore_secrets(target, data, "long backup passphrase")
    assert (target / "smtp_password").read_text(encoding="utf-8") == "different"


def test_secret_backup_rejects_tampering_and_short_passphrases(tmp_path):
    (tmp_path / "data_encryption_key").write_text(base64.b64encode(b"x" * 32).decode(), encoding="ascii")
    with pytest.raises(ValueError, match="at least 12"):
        export_secrets(tmp_path, "short")
    data = export_secrets(tmp_path, "long backup passphrase")
    with pytest.raises(ValueError, match="damaged"):
        restore_secrets(tmp_path / "restore", data[:-1] + bytes([data[-1] ^ 1]), "long backup passphrase")


def test_secret_backup_cli_uses_private_file_and_refuses_overwrite(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source"
    source.mkdir()
    key = base64.b64encode(b"x" * 32).decode()
    (source / "data_encryption_key").write_text(key, encoding="ascii")
    backup = tmp_path / "secrets.cpkeys"
    monkeypatch.setenv("CLINICPULSE_MANAGED_KEY_FILE", str(source / "data_encryption_key"))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "long backup passphrase")
    monkeypatch.setattr("sys.argv", ["managed_secrets", "export", str(backup)])
    assert main() == 0
    assert backup.stat().st_mode & 0o777 == 0o600
    assert key not in capsys.readouterr().out
    assert main() == 1
    target = tmp_path / "target"
    monkeypatch.setenv("CLINICPULSE_MANAGED_KEY_FILE", str(target / "data_encryption_key"))
    monkeypatch.setattr("sys.argv", ["managed_secrets", "import", str(backup)])
    assert main() == 0
    assert (target / "data_encryption_key").read_text(encoding="ascii") == key


def test_secret_backup_cli_exports_external_key_and_rejects_external_import(monkeypatch, tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    external = tmp_path / "external-key"
    expected_key = base64.b64encode(b"e" * 32).decode()
    external.write_text(expected_key, encoding="ascii")
    (managed / "data_encryption_key").write_text(base64.b64encode(b"m" * 32).decode(), encoding="ascii")
    (managed / "smtp_password").write_text("smtp-password", encoding="utf-8")
    backup = tmp_path / "backup.cpkeys"
    monkeypatch.setenv("CLINICPULSE_MANAGED_KEY_FILE", str(managed / "data_encryption_key"))
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", str(external))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "long backup passphrase")
    monkeypatch.setattr("sys.argv", ["managed_secrets", "export", str(backup)])
    assert main() == 0
    restored = tmp_path / "restore"
    restore_secrets(restored, backup.read_bytes(), "long backup passphrase")
    assert (restored / "data_encryption_key").read_text(encoding="ascii") == expected_key
    assert (restored / "smtp_password").read_text(encoding="utf-8") == "smtp-password"
    monkeypatch.setattr("sys.argv", ["managed_secrets", "import", str(backup)])
    assert main() == 1
    assert external.read_text(encoding="ascii") == expected_key


def test_secret_backup_restores_external_key_to_private_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    key = base64.b64encode(b"z" * 32).decode()
    (source / "data_encryption_key").write_text(key, encoding="ascii")
    (source / "smtp_password").write_text("mail-secret", encoding="utf-8")
    backup = export_secrets(source, "long backup passphrase")
    external = tmp_path / "external"
    external.mkdir(mode=0o700)
    managed = tmp_path / "managed"
    restore_secrets(managed, backup, "long backup passphrase", external)
    assert (external / "data_encryption_key").read_text(encoding="ascii") == key
    assert (external / "data_encryption_key").stat().st_mode & 0o777 == 0o600
    assert (managed / "smtp_password").read_text(encoding="utf-8") == "mail-secret"
    assert not (managed / "data_encryption_key").exists()
    external.chmod(0o755)
    with pytest.raises(ValueError, match="must exist and be private"):
        restore_secrets(managed, backup, "long backup passphrase", external)


def test_secret_backup_cli_uses_configured_smtp_file(monkeypatch, tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "data_encryption_key").write_text(base64.b64encode(b"x" * 32).decode(), encoding="ascii")
    (managed / "smtp_password").write_text("old-smtp", encoding="utf-8")
    external_smtp = tmp_path / "smtp"
    external_smtp.write_text("actual-smtp", encoding="utf-8")
    backup = tmp_path / "backup.cpkeys"
    monkeypatch.setenv("CLINICPULSE_MANAGED_KEY_FILE", str(managed / "data_encryption_key"))
    monkeypatch.delenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", raising=False)
    monkeypatch.setenv("CLINICPULSE_SMTP_PASSWORD_FILE", str(external_smtp))
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "long backup passphrase")
    monkeypatch.setattr("sys.argv", ["managed_secrets", "export", str(backup)])
    assert main() == 0
    target = tmp_path / "target"
    restore_secrets(target, backup.read_bytes(), "long backup passphrase")
    assert (target / "smtp_password").read_text(encoding="utf-8") == "actual-smtp"