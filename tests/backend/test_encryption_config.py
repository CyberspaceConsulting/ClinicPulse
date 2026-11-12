import base64

import pytest

from app.encrypted import ensure_managed_key, load_encryption_key


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "not configured"),
        ("not base64!", "base64 encoded"),
        (base64.b64encode(b"too short").decode(), "at least 32"),
    ],
)
def test_invalid_database_encryption_key_is_rejected(monkeypatch, value, message):
    monkeypatch.delenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", raising=False)
    if value is None:
        monkeypatch.delenv("CLINICPULSE_DATA_ENCRYPTION_KEY", raising=False)
    else:
        monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY", value)
    with pytest.raises(RuntimeError, match=message):
        load_encryption_key()


def test_missing_key_file_is_not_replaced_by_environment_key(monkeypatch, tmp_path):
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY", base64.b64encode(b"x" * 32).decode())
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="cannot be read"):
        load_encryption_key()


def test_key_file_is_loaded(monkeypatch, tmp_path):
    key = base64.b64encode(b"x" * 32).decode()
    key_file = tmp_path / "key"
    key_file.write_text(key + "\n", encoding="ascii")
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", str(key_file))
    assert load_encryption_key() == key


def test_managed_key_is_generated_once_and_reused(monkeypatch, tmp_path):
    key_file = tmp_path / "managed" / "key"
    ensure_managed_key(str(key_file), lambda: False)
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", str(key_file))
    first_key = load_encryption_key()
    assert len(base64.b64decode(first_key)) == 48
    assert key_file.stat().st_mode & 0o777 == 0o600
    ensure_managed_key(str(key_file), lambda: True)
    assert load_encryption_key() == first_key


def test_managed_key_is_not_generated_for_existing_database(tmp_path):
    key_file = tmp_path / "managed" / "key"
    with pytest.raises(RuntimeError, match="restore the original key"):
        ensure_managed_key(str(key_file), lambda: True)
    assert not key_file.exists()
