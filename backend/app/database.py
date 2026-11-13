import os
import base64
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .encrypted import SQLITE_TEST_KEY, ensure_managed_key, load_encryption_key


class Base(DeclarativeBase):
    pass


database_url = os.environ.get("DATABASE_URL", "sqlite:///./medora.db")
if os.environ.get("DB_HOST"):
    database_url = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("DB_USER", "medora"),
        password=os.environ.get("DB_PASSWORD") or None,
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ.get("DB_NAME", "medora"),
    )
engine_options: dict[str, object] = {"pool_pre_ping": True}
if str(database_url).startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    if str(database_url).endswith(":memory:"):
        engine_options["poolclass"] = StaticPool

engine = create_engine(database_url, **engine_options)
if engine.dialect.name == "sqlite" and not str(database_url).endswith(":memory:"):
    raise RuntimeError("SQLite is supported only for in-memory tests; Medora requires PostgreSQL")

managed_key_file = os.environ.get("MEDORA_MANAGED_KEY_FILE")
if (engine.dialect.name == "postgresql" and managed_key_file
        and not os.environ.get("MEDORA_DATA_ENCRYPTION_KEY_FILE")
        and not os.environ.get("MEDORA_DATA_ENCRYPTION_KEY")):
    ensure_managed_key(managed_key_file, lambda: bool(inspect(engine).get_table_names()))
    engine.dispose()
    os.environ["MEDORA_DATA_ENCRYPTION_KEY_FILE"] = managed_key_file

managed_smtp_file = os.environ.get("MEDORA_MANAGED_SMTP_PASSWORD_FILE")
smtp_file = os.environ.get("MEDORA_SMTP_PASSWORD_FILE")
if managed_smtp_file and smtp_file in (None, "", "/run/secrets/smtp_password"):
    smtp_path = Path(managed_smtp_file)
    smtp_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    smtp_path.touch(mode=0o600, exist_ok=True)
    os.environ["MEDORA_SMTP_PASSWORD_FILE"] = managed_smtp_file


@event.listens_for(engine, "connect")
def configure_database_encryption(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name == "postgresql":
        key = load_encryption_key()
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(
                "SELECT set_config('medora.data_encryption_key', %s, false)",
                (key,),
            )
            # Without a commit, a later rollback would revert the session setting.
            dbapi_connection.commit()
        finally:
            cursor.close()
        return
    if engine.dialect.name == "sqlite":
        dbapi_connection.create_function("current_setting", 1, lambda _name: SQLITE_TEST_KEY)
        dbapi_connection.create_function(
            "pgp_sym_encrypt",
            2,
            lambda value, _key: value.encode("utf-8") if value is not None else None,
        )
        dbapi_connection.create_function(
            "pgp_sym_decrypt",
            2,
            lambda value, _key: value.decode("utf-8") if value is not None else None,
        )
        dbapi_connection.create_function(
            "encode",
            2,
            lambda value, _format: base64.b64encode(value).decode("ascii") if value is not None else None,
        )
        dbapi_connection.create_function(
            "decode",
            2,
            lambda value, _format: base64.b64decode(value) if value is not None else None,
        )
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
