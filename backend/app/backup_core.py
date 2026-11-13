"""Encrypted logical backups: export all tables as JSON, restore them into any installation.

Values are exported decrypted and re-encrypted on import, so a backup can be restored
with a different data encryption key (for example on a new server).
"""
import base64
import binascii
import gzip
import hashlib
import json
import logging
import os
import threading
from datetime import date, datetime, time, timezone
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import Table, delete, func, select, text, update
from sqlalchemy.orm import Session

from . import models
from .database import Base
from .encrypted import username_lookup_digest
from .update_checker import APP_VERSION

logger = logging.getLogger(__name__)

MAGIC = b"CPBK2\n"
FORMAT_VERSION = 1
NONCE_LENGTH = 12
MIN_PASSPHRASE_LENGTH = 12
PUBLIC_PREFIX = "CPPUB1:"
KEYFILE_HEADER = "MEDORA RECOVERY KEY v1"
LEGACY_KEYFILE_HEADER = "CLINICPULSE RECOVERY KEY v1"
FILE_PREFIX = "medora-"
LEGACY_FILE_PREFIX = "clinicpulse-"
FILE_SUFFIX = ".cpbak"
EXCLUDED_TABLES = {"backup_runs", "login_attempts", "backup_recipients"}
WRAP_INFO = b"medora-backup-wrap-v2"
LEGACY_WRAP_INFO = b"clinicpulse-backup-wrap-v2"
MAX_HEADER_BYTES = 256 * 1024

# Serializes backups and restores so a restore never runs against a half-written export.
backup_lock = threading.Lock()


class BackupError(Exception):
    pass


def validate_passphrase(passphrase: str) -> None:
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise BackupError(f"Das Passwort muss mindestens {MIN_PASSPHRASE_LENGTH} Zeichen lang sein")


def backup_filename(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"{FILE_PREFIX}{stamp}{FILE_SUFFIX}"


def is_backup_filename(name: str) -> bool:
    return name.startswith((FILE_PREFIX, LEGACY_FILE_PREFIX)) and name.endswith(FILE_SUFFIX) and "/" not in name and "\\" not in name


def _raw_public(key: X25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def _raw_private(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def format_public_key(raw: bytes) -> str:
    return PUBLIC_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_public_key(value: str) -> X25519PublicKey:
    value = value.strip()
    if not value.startswith(PUBLIC_PREFIX):
        raise BackupError("Ungültiger öffentlicher Schlüssel (erwartet wird ein Wert, der mit CPPUB1: beginnt)")
    try:
        raw = base64.urlsafe_b64decode(value[len(PUBLIC_PREFIX):] + "=" * (-len(value) % 4))
        if len(raw) != 32:
            raise ValueError
        return X25519PublicKey.from_public_bytes(raw)
    except (ValueError, binascii.Error) as exc:
        raise BackupError("Ungültiger öffentlicher Schlüssel") from exc


def key_id(public: X25519PublicKey) -> str:
    return hashlib.sha256(_raw_public(public)).hexdigest()[:16]


def _scrypt(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def generate_recovery_key(passphrase: str) -> tuple[str, bytes]:
    """Create a key pair. The private key leaves the server only inside a passphrase-protected file."""
    validate_passphrase(passphrase)
    private = X25519PrivateKey.generate()
    public_text = format_public_key(_raw_public(private.public_key()))
    salt, nonce = os.urandom(16), os.urandom(NONCE_LENGTH)
    sealed = AESGCM(_scrypt(passphrase, salt)).encrypt(nonce, _raw_private(private), public_text.encode("ascii"))
    body = base64.b64encode(salt + nonce + sealed).decode("ascii")
    return public_text, f"{KEYFILE_HEADER}\npublic: {public_text}\ndata: {body}\n".encode("ascii")


def load_recovery_key(key_file: bytes | str, passphrase: str) -> X25519PrivateKey:
    text = key_file.decode("utf-8", "replace") if isinstance(key_file, bytes) else key_file
    fields = dict(
        line.split(": ", 1) for line in text.strip().splitlines()[1:] if ": " in line
    )
    if not text.strip().startswith((KEYFILE_HEADER, LEGACY_KEYFILE_HEADER)) or "public" not in fields or "data" not in fields:
        raise BackupError("Das ist keine gültige Wiederherstellungsschlüssel-Datei")
    try:
        blob = base64.b64decode(fields["data"], validate=True)
        salt, nonce, sealed = blob[:16], blob[16:16 + NONCE_LENGTH], blob[16 + NONCE_LENGTH:]
        raw = AESGCM(_scrypt(passphrase, salt)).decrypt(nonce, sealed, fields["public"].encode("ascii"))
        return X25519PrivateKey.from_private_bytes(raw)
    except InvalidTag as exc:
        raise BackupError("Passwort der Schlüsseldatei ist falsch") from exc
    except (ValueError, binascii.Error) as exc:
        raise BackupError("Die Schlüsseldatei ist beschädigt") from exc


def _wrap_key(shared: bytes, ephemeral_public: bytes, recipient_public: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info + ephemeral_public + recipient_public).derive(shared)


def _backup_tables() -> list[Table]:
    return [table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES]


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$d": value.isoformat()}
    if isinstance(value, time):
        return {"$t": value.isoformat()}
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise BackupError("Binärwerte werden im Backup nicht unterstützt")
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if "$dt" in value:
            return datetime.fromisoformat(value["$dt"])
        if "$d" in value:
            return date.fromisoformat(value["$d"])
        if "$t" in value:
            return time.fromisoformat(value["$t"])
    return value


def export_payload(db: Session) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    connection = db.connection()
    for table in _backup_tables():
        columns = [column.name for column in table.columns]
        rows = connection.execute(select(*table.columns)).all()
        tables[table.name] = {
            "columns": columns,
            "rows": [[_encode(value) for value in row] for row in rows],
        }
    return {
        "format": FORMAT_VERSION,
        "app_version": APP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }


def encrypt_payload(payload: dict[str, Any], public_keys: list[str]) -> bytes:
    recipients = [parse_public_key(item) for item in dict.fromkeys(public_keys)]
    if not recipients:
        raise BackupError("Es ist kein Empfänger-Schlüssel hinterlegt – ein Backup wird nie unverschlüsselt erstellt")
    plaintext = gzip.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    content_key = AESGCM.generate_key(bit_length=256)
    slots = []
    for recipient in recipients:
        ephemeral = X25519PrivateKey.generate()
        ephemeral_public = _raw_public(ephemeral.public_key())
        wrap = _wrap_key(ephemeral.exchange(recipient), ephemeral_public, _raw_public(recipient), WRAP_INFO)
        nonce = os.urandom(NONCE_LENGTH)
        slots.append({
            "kid": key_id(recipient),
            "epk": base64.b64encode(ephemeral_public).decode("ascii"),
            "n": base64.b64encode(nonce).decode("ascii"),
            "wk": base64.b64encode(AESGCM(wrap).encrypt(nonce, content_key, MAGIC)).decode("ascii"),
        })
    header = json.dumps({"slots": slots}, separators=(",", ":")).encode("utf-8")
    framed = MAGIC + len(header).to_bytes(4, "big") + header
    nonce = os.urandom(NONCE_LENGTH)
    return framed + nonce + AESGCM(content_key).encrypt(nonce, plaintext, framed)


def decrypt_payload(data: bytes, private_key: X25519PrivateKey) -> dict[str, Any]:
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 4:
        raise BackupError("Die Datei ist kein Medora-Backup")
    header_length = int.from_bytes(data[len(MAGIC):len(MAGIC) + 4], "big")
    header_end = len(MAGIC) + 4 + header_length
    if header_length > MAX_HEADER_BYTES or len(data) < header_end + NONCE_LENGTH + 16:
        raise BackupError("Die Backup-Datei ist beschädigt")
    framed = data[:header_end]
    own_public = _raw_public(private_key.public_key())
    try:
        slots = json.loads(data[len(MAGIC) + 4:header_end])["slots"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BackupError("Die Backup-Datei ist beschädigt") from exc
    own_id = key_id(private_key.public_key())
    slot = next((item for item in slots if isinstance(item, dict) and item.get("kid") == own_id), None)
    if slot is None:
        raise BackupError("Dieses Backup wurde nicht für diese Instanz bzw. diesen Schlüssel verschlüsselt")
    try:
        ephemeral_public = base64.b64decode(slot["epk"])
        shared = private_key.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
        wrapped_key = base64.b64decode(slot["wk"])
        wrap_nonce = base64.b64decode(slot["n"])
        for wrap_info in (WRAP_INFO, LEGACY_WRAP_INFO):
            wrap = _wrap_key(shared, ephemeral_public, own_public, wrap_info)
            try:
                content_key = AESGCM(wrap).decrypt(wrap_nonce, wrapped_key, MAGIC)
                break
            except InvalidTag:
                if wrap_info == LEGACY_WRAP_INFO:
                    raise
        nonce = data[header_end:header_end + NONCE_LENGTH]
        plaintext = AESGCM(content_key).decrypt(nonce, data[header_end + NONCE_LENGTH:], framed)
        payload = json.loads(gzip.decompress(plaintext))
    except (InvalidTag, KeyError, ValueError, TypeError, binascii.Error, OSError, EOFError) as exc:
        raise BackupError("Backup beschädigt oder manipuliert") from exc
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_VERSION:
        raise BackupError("Nicht unterstütztes Backup-Format")
    return payload


def create_backup(db: Session, public_keys: list[str]) -> bytes:
    for item in public_keys:
        parse_public_key(item)
    if not public_keys:
        raise BackupError("Es ist kein Empfänger-Schlüssel hinterlegt – ein Backup wird nie unverschlüsselt erstellt")
    with backup_lock:
        return encrypt_payload(export_payload(db), public_keys)


def _validate_payload(payload: dict[str, Any]) -> dict[str, tuple[Table, dict[str, Any]]]:
    tables = {table.name: table for table in _backup_tables()}
    stored = payload.get("tables")
    if not isinstance(stored, dict):
        raise BackupError("Die Backup-Datei ist beschädigt")
    result: dict[str, tuple[Table, dict[str, Any]]] = {}
    for name, entry in stored.items():
        if name in EXCLUDED_TABLES:
            continue
        table = tables.get(name)
        if table is None:
            raise BackupError(f"Das Backup enthält die unbekannte Tabelle „{name}“ – wahrscheinlich stammt es aus einer neueren Medora-Version")
        unknown = [column for column in entry["columns"] if column not in table.columns]
        if unknown:
            raise BackupError(f"Das Backup enthält unbekannte Spalten in „{name}“ – bitte zuerst Medora aktualisieren")
        result[name] = (table, entry)
    return result


def _reset_sequences(db: Session, tables: list[Table]) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    for table in tables:
        if len(table.primary_key.columns) != 1:
            continue
        for column in table.primary_key.columns:
            if column.autoincrement is False or str(column.type) != "INTEGER":
                continue
            db.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table, :column), "
                    "COALESCE((SELECT MAX({col}) FROM {tbl}), 1), "
                    "(SELECT MAX({col}) IS NOT NULL FROM {tbl}))".format(col=f'"{column.name}"', tbl=f'"{table.name}"')
                ),
                {"table": table.name, "column": column.name},
            )


def _refresh_username_lookups(db: Session) -> None:
    # The lookup digest is keyed with this installation's data key, so it must be recomputed.
    for model in (models.AdminAccount, models.UserAccount):
        table = model.__table__
        for row in db.execute(select(table.c.id, table.c.username)).all():
            db.execute(update(table).where(table.c.id == row.id).values(username_lookup=username_lookup_digest(row.username)))


def restore_backup(db: Session, data: bytes, private_key: X25519PrivateKey, actor: str) -> dict[str, int]:
    payload = decrypt_payload(data, private_key)
    with backup_lock:
        prepared = _validate_payload(payload)
        ordered = [table for table in _backup_tables() if table.name in prepared]
        counts: dict[str, int] = {}
        try:
            for table in reversed(_backup_tables()):
                db.execute(delete(table))
            for table in ordered:
                entry = prepared[table.name][1]
                columns = entry["columns"]
                rows = [{column: _decode(value) for column, value in zip(columns, row)} for row in entry["rows"]]
                if rows:
                    db.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            _reset_sequences(db, ordered)
            _refresh_username_lookups(db)
            db.add(models.AuditEvent(
                created_at=datetime.now(timezone.utc),
                actor_username=actor[:64],
                action="restored",
                entity_type="Backup",
                entity_id=str(payload.get("created_at", ""))[:64] or "unknown",
            ))
            db.commit()
        except BackupError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            logger.exception("Backup restore failed")
            raise BackupError("Die Wiederherstellung ist fehlgeschlagen; es wurden keine Daten verändert") from exc
        return counts


def backup_summary(db: Session) -> dict[str, int]:
    return {table.name: db.scalar(select(func.count()).select_from(table)) or 0 for table in _backup_tables()}
