import base64
import binascii
import hashlib
import hmac
import os
from pathlib import Path

from sqlalchemy import String, Text, case, func, literal
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator


SQLITE_TEST_KEY = "clinicpulse-sqlite-tests-only"


def load_encryption_key() -> str:
    key_file = os.environ.get("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE")
    key = os.environ.get("CLINICPULSE_DATA_ENCRYPTION_KEY")
    if key_file:
        try:
            key = Path(key_file).read_text(encoding="ascii").strip()
        except OSError as exc:
            raise RuntimeError("Configured data encryption key file cannot be read") from exc
    if not key:
        raise RuntimeError("ClinicPulse data encryption key is not configured")
    try:
        decoded = base64.b64decode(key, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("ClinicPulse data encryption key must be base64 encoded") from exc
    if len(decoded) < 32:
        raise RuntimeError("ClinicPulse data encryption key must contain at least 32 random bytes")
    return key


def username_lookup_digest(username: str, key: str | None = None) -> str:
    encryption_key = key or os.environ.get("CLINICPULSE_DATA_ENCRYPTION_KEY")
    key_file = os.environ.get("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE")
    if key_file:
        try:
            encryption_key = Path(key_file).read_text(encoding="ascii").strip()
        except OSError as exc:
            raise RuntimeError("Configured data encryption key file cannot be read") from exc
    if not encryption_key:
        encryption_key = SQLITE_TEST_KEY
    index_key = hmac.digest(encryption_key.encode("ascii"), b"clinicpulse-username-index-v1", "sha256")
    return hmac.new(index_key, username.encode("utf-8"), hashlib.sha256).hexdigest()


class EncryptedText(TypeDecorator[str]):
    impl = Text
    cache_ok = True

    def bind_expression(self, bindvalue: ColumnElement[str]) -> ColumnElement[str]:
        return case(
            (bindvalue.is_(None), None),
            else_=func.encode(
                func.pgp_sym_encrypt(
                    bindvalue,
                    func.current_setting("clinicpulse.data_encryption_key"),
                ),
                literal("base64"),
            ),
        )

    def column_expression(self, column: ColumnElement[str]) -> ColumnElement[str]:
        return func.pgp_sym_decrypt(
            func.decode(column, literal("base64")),
            func.current_setting("clinicpulse.data_encryption_key"),
            type_=String(),
        )
