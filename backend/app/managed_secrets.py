import argparse
import base64
import binascii
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"CLINICPULSE-KEYS-1\n"
MIN_PASSPHRASE_LENGTH = 12


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise ValueError("Password must contain at least 12 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def _validate_key(value: str) -> None:
    try:
        decoded = base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Invalid encryption key") from exc
    if len(decoded) < 32:
        raise ValueError("Invalid encryption key")


def export_secrets(directory: Path, passphrase: str, key_file: Path | None = None, smtp_file: Path | None = None) -> bytes:
    key = (key_file or directory / "data_encryption_key").read_text(encoding="ascii")
    _validate_key(key)
    managed_smtp = directory / "smtp_password"
    smtp = smtp_file.read_text(encoding="utf-8") if smtp_file else (
        managed_smtp.read_text(encoding="utf-8") if managed_smtp.exists() else None
    )
    payload = json.dumps({"data_encryption_key": key, "smtp_password": smtp}).encode("utf-8")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    encrypted = AESGCM(_derive_key(passphrase, salt)).encrypt(nonce, payload, MAGIC)
    return MAGIC + salt + nonce + encrypted


def restore_secrets(directory: Path, data: bytes, passphrase: str, key_directory: Path | None = None) -> None:
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 16 + 12 + 16:
        raise ValueError("Invalid secret backup")
    offset = len(MAGIC)
    salt, nonce, ciphertext = data[offset:offset + 16], data[offset + 16:offset + 28], data[offset + 28:]
    try:
        plaintext = AESGCM(_derive_key(passphrase, salt)).decrypt(nonce, ciphertext, MAGIC)
        payload = json.loads(plaintext)
    except (InvalidTag, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Incorrect password or damaged secret backup") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data_encryption_key"), str):
        raise ValueError("Invalid secret backup")
    _validate_key(payload["data_encryption_key"])
    smtp = payload.get("smtp_password")
    if smtp is not None and not isinstance(smtp, str):
        raise ValueError("Invalid secret backup")
    values = {(key_directory or directory) / "data_encryption_key": payload["data_encryption_key"]}
    if smtp is not None:
        values[directory / "smtp_password"] = smtp
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    if key_directory is not None:
        if not key_directory.is_dir() or key_directory.stat().st_mode & 0o077:
            raise ValueError("External recovery directory must exist and be private")
    for path, value in values.items():
        if path.exists() and path.read_text(encoding="utf-8") != value:
            raise ValueError("Existing managed secrets differ; refusing to overwrite them")
    for path, value in values.items():
        if path.exists():
            continue
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(value)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != value:
                    raise ValueError("Existing managed secrets differ; refusing to overwrite them")
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted backup of managed ClinicPulse secrets")
    parser.add_argument("action", choices=("export", "import"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--key-directory", type=Path, help="Existing private directory for external-key recovery")
    args = parser.parse_args()
    directory = Path(os.environ.get("CLINICPULSE_MANAGED_KEY_FILE", "/var/lib/clinicpulse-secrets/data_encryption_key")).parent
    external_key = os.environ.get("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE")
    configured_smtp = os.environ.get("CLINICPULSE_SMTP_PASSWORD_FILE")
    smtp_file = Path(configured_smtp) if configured_smtp not in (None, "", "/run/secrets/smtp_password") else None
    try:
        if args.action == "export" and args.key_directory is not None:
            raise ValueError("--key-directory is only available for import")
        if args.action == "import" and external_key and args.key_directory is None:
            raise ValueError("Import to an external key requires a separate recovery directory")
        passphrase = getpass.getpass("Passwort für die Schlüsseldatei: ")
        if args.action == "export":
            if passphrase != getpass.getpass("Passwort wiederholen: "):
                raise ValueError("Passwords do not match")
            data = export_secrets(directory, passphrase, Path(external_key) if external_key else None, smtp_file)
            descriptor = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
        else:
            restore_secrets(directory, args.file.read_bytes(), passphrase, args.key_directory)
        print("Vorgang abgeschlossen.")
    except (OSError, ValueError) as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())