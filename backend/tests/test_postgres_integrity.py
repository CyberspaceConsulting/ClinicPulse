"""PostgreSQL-only checks; each test owns a temporary database schema."""

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app import backup_core, main, models
from app.database import Base
from app.encrypted import username_lookup_digest
from app.schemas import AssignmentCreate
from app.security import Principal, authenticate, hash_password


@pytest.fixture
def postgres_db(monkeypatch):
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to a disposable PostgreSQL test database")

    key = base64.b64encode(b"test-only-database-key-32-bytes!").decode("ascii")
    monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY", key)
    monkeypatch.delenv("CLINICPULSE_DATA_ENCRYPTION_KEY_FILE", raising=False)
    schema = f"clinicpulse_test_{uuid4().hex}"
    admin_engine = create_engine(url)
    if admin_engine.dialect.name != "postgresql":
        admin_engine.dispose()
        pytest.fail("TEST_POSTGRES_URL must point to PostgreSQL")
    with admin_engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')

    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, _record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}", public')
            cursor.execute("SELECT set_config('clinicpulse.data_encryption_key', %s, false)", (key,))
        dbapi_connection.commit()

    try:
        Base.metadata.create_all(engine)
        monkeypatch.setattr(main, "engine", engine)
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin_engine.dispose()


def _seed_legacy_plaintext(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE admin_account DROP COLUMN username_lookup CASCADE")
        connection.exec_driver_sql("ALTER TABLE user_accounts DROP COLUMN username_lookup CASCADE")
        connection.execute(text(
            "INSERT INTO admin_account "
            "(id, username, password_salt, password_hash, signing_key, license_token, "
            "profile_photo_visibility, token_version) "
            "VALUES (1, :name, 'salt', 'hash', 'signing-secret', 'license-secret', 'private', 0)"
        ), {"name": "legacy-admin"})
        connection.execute(text(
            "INSERT INTO employees (id, name, role) VALUES (10, :name, 'Nurse')"
        ), {"name": "Legacy Person"})


def test_legacy_migration_encrypts_data_and_is_idempotent(postgres_db):
    _seed_legacy_plaintext(postgres_db)
    main.migrate_existing_database()
    with postgres_db.connect() as connection:
        stored = connection.execute(text(
            "SELECT username, username_lookup, signing_key, license_token FROM admin_account WHERE id = 1"
        )).one()
        employee_ciphertext = connection.scalar(text("SELECT name FROM employees WHERE id = 10"))
        assert stored.username != "legacy-admin"
        assert stored.username_lookup == username_lookup_digest("legacy-admin")
        assert stored.signing_key != "signing-secret"
        assert stored.license_token != "license-secret"
        assert employee_ciphertext != "Legacy Person"
    with Session(postgres_db) as session:
        admin = session.get(models.AdminAccount, 1)
        assert (admin.username, admin.signing_key, admin.license_token) == (
            "legacy-admin", "signing-secret", "license-secret"
        )
        assert session.get(models.Employee, 10).name == "Legacy Person"

    main.migrate_existing_database()
    with postgres_db.connect() as connection:
        assert connection.execute(text(
            "SELECT username, username_lookup, signing_key, license_token FROM admin_account WHERE id = 1"
        )).one() == stored
        assert connection.scalar(text("SELECT count(*) FROM clinicpulse_schema_migrations WHERE version = 1")) == 1


def test_failed_encryption_migration_rolls_back_legacy_data(postgres_db):
    _seed_legacy_plaintext(postgres_db)

    def fail_after_admin_update(_connection, _cursor, statement, _parameters, _context, _executemany):
        if "UPDATE employees" in statement:
            raise ValueError("simulated migration failure")

    event.listen(postgres_db, "before_cursor_execute", fail_after_admin_update)
    try:
        with pytest.raises(ValueError, match="simulated migration failure"):
            main._migrate_encrypted_columns()
    finally:
        event.remove(postgres_db, "before_cursor_execute", fail_after_admin_update)
    assert "username_lookup" not in {column["name"] for column in inspect(postgres_db).get_columns("admin_account")}
    with postgres_db.connect() as connection:
        assert connection.scalar(text("SELECT username FROM admin_account WHERE id = 1")) == "legacy-admin"
        assert connection.scalar(text("SELECT name FROM employees WHERE id = 10")) == "Legacy Person"
        assert not inspect(connection).has_table("clinicpulse_schema_migrations")


def test_encrypted_value_rejects_wrong_key(postgres_db):
    with Session(postgres_db) as session:
        session.add(models.Employee(id=1, name="Protected Person", role="Nurse"))
        session.commit()
    with postgres_db.connect() as connection:
        with pytest.raises(DBAPIError) as error:
            connection.execute(text(
                "SELECT pgp_sym_decrypt(decode(name, 'base64'), :wrong_key) "
                "FROM employees WHERE id = 1"
            ), {"wrong_key": "wrong-test-key"})
        assert "Wrong key or corrupt data" in str(error.value)


def test_upgrade_from_legacy_schema_preserves_existing_data(postgres_db):
    Base.metadata.drop_all(postgres_db)
    Base.metadata.create_all(postgres_db)
    password_salt, password_hash = hash_password("old-test-password")
    with postgres_db.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE admin_account DROP COLUMN username_lookup CASCADE")
        connection.exec_driver_sql("ALTER TABLE user_accounts DROP COLUMN username_lookup CASCADE")
        connection.execute(text(
            "INSERT INTO admin_account "
            "(id, username, password_salt, password_hash, signing_key, license_token, "
            "profile_photo_visibility, token_version) "
            "VALUES (1, 'old-admin', :salt, :password_hash, 'old-secret', 'old-license', 'private', 0)"
        ), {"salt": password_salt, "password_hash": password_hash})
        connection.execute(text(
            "INSERT INTO employees (id, name, role) VALUES (10, 'Old Person', 'Nurse')"
        ))
    with Session(postgres_db) as session:
        department = models.Department(name="Old department")
        shift = models.ShiftType(
            name="Old shift",
            start_time=time(7),
            end_time=time(15),
            department=department,
        )
        session.add_all([department, shift])
        session.flush()
        session.execute(
            text("UPDATE employees SET department_id = :department_id WHERE id = 10"),
            {"department_id": department.id},
        )
        session.add(models.Assignment(
            employee_id=10,
            shift_type_id=shift.id,
            starts_at=datetime(2026, 1, 1, 7, tzinfo=timezone.utc),
            ends_at=datetime(2026, 1, 1, 15, tzinfo=timezone.utc),
        ))
        session.commit()
    Base.metadata.create_all(postgres_db)
    main.migrate_existing_database()
    main.migrate_existing_database()
    with Session(postgres_db) as session:
        assert session.get(models.AdminAccount, 1).username == "old-admin"
        assert authenticate(session, "old-admin", "old-test-password") is not None
        employee = session.scalar(select(models.Employee))
        assignment = session.scalar(select(models.Assignment))
        assert (employee.name, employee.first_name, employee.last_name) == ("Old Person", None, None)
        assert employee.department.name == "Old department"
        assert assignment.employee_id == employee.id
        assert assignment.shift_type.name == "Old shift"
        assert assignment.starts_at == datetime(2026, 1, 1, 7, tzinfo=timezone.utc)


def test_backup_restores_across_distinct_database_keys(postgres_db, monkeypatch):
    main._migrate_encrypted_columns()
    original_key = os.environ["CLINICPULSE_DATA_ENCRYPTION_KEY"]
    new_key = base64.b64encode(b"another-test-database-key-32-byte").decode("ascii")
    public_key, key_file = backup_core.generate_recovery_key("test-passphrase-long")
    private_key = backup_core.load_recovery_key(key_file, "test-passphrase-long")
    with Session(postgres_db) as session:
        session.add(models.AdminAccount(
            id=1, username="restore-admin", username_lookup=username_lookup_digest("restore-admin"),
            password_salt="salt", password_hash="hash", signing_key="secret", license_token="token",
        ))
        session.commit()
        backup = backup_core.encrypt_payload(backup_core.export_payload(session), [public_key])
        session.execute(text("SELECT set_config('clinicpulse.data_encryption_key', :key, false)"), {"key": new_key})
        monkeypatch.setenv("CLINICPULSE_DATA_ENCRYPTION_KEY", new_key)
        try:
            backup_core.restore_backup(session, backup, private_key, "restore-admin")
            session.expire_all()
            admin = session.get(models.AdminAccount, 1)
            assert admin.username == "restore-admin"
            assert admin.username_lookup == username_lookup_digest("restore-admin")
            assert admin.username_lookup != username_lookup_digest("restore-admin", original_key)
        finally:
            session.execute(text("SELECT set_config('clinicpulse.data_encryption_key', :key, false)"), {"key": original_key})
            session.commit()


def test_concurrent_assignments_for_same_employee_do_not_overlap(postgres_db):
    main._migrate_encrypted_columns()
    with Session(postgres_db) as session:
        session.add(models.BusinessConfiguration(
            id=1, federal_state="Nordrhein-Westfalen", operational_profile="hospital",
            timezone="Europe/Berlin",
        ))
        department = models.Department(name="Concurrency test")
        session.add(department)
        session.flush()
        employee = models.Employee(name="Test Person", role="Nurse", department_id=department.id)
        shift = models.ShiftType(
            name="Day", start_time=datetime.strptime("07:00", "%H:%M").time(),
            end_time=datetime.strptime("15:00", "%H:%M").time(), position="Nurse",
            required_staff=2, break_minutes=30, break_start_minutes=240, department_id=department.id,
        )
        session.add_all([employee, shift])
        session.commit()
        assignment = AssignmentCreate(
            employee_id=employee.id, shift_type_id=shift.id,
            starts_at=datetime(2026, 10, 14, 5, tzinfo=timezone.utc),
            ends_at=datetime(2026, 10, 14, 13, tzinfo=timezone.utc),
        )
    principal = Principal("test-planner", "ADMIN", None, True, True, True, True)
    barrier = Barrier(2, timeout=10)

    def assign():
        with Session(postgres_db) as session:
            barrier.wait()
            try:
                main.create_assignment(assignment, principal, session)
                return (201, "")
            except HTTPException as exc:
                return (exc.status_code, exc.detail)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: assign(), range(2)))
    assert sorted(status for status, _ in outcomes) == [201, 409], outcomes
    with Session(postgres_db) as session:
        assert len(session.scalars(select(models.Assignment)).all()) == 1


def test_postgres_backup_restore_and_failed_restore_are_atomic(postgres_db):
    main._migrate_encrypted_columns()
    public_key, key_file = backup_core.generate_recovery_key("test-passphrase-long")
    private_key = backup_core.load_recovery_key(key_file, "test-passphrase-long")
    with Session(postgres_db) as session:
        department = models.Department(name="Testabteilung")
        session.add(department)
        session.flush()
        session.add(models.Employee(id=10, name="Test Person", role="Nurse", department_id=department.id))
        session.commit()
        payload = backup_core.export_payload(session)
        backup = backup_core.encrypt_payload(payload, [public_key])
        assert b"Test Person" not in backup

        session.get(models.Employee, 10).name = "Changed Person"
        session.commit()
        backup_core.restore_backup(session, backup, private_key, "test-admin")
        session.expire_all()
        assert session.get(models.Employee, 10).name == "Test Person"
        next_employee = models.Employee(name="Next Person", role="Nurse")
        session.add(next_employee)
        session.commit()
        assert next_employee.id > 10

        employees = payload["tables"]["employees"]
        department_column = employees["columns"].index("department_id")
        employees["rows"][0][department_column] = 999999
        invalid_backup = backup_core.encrypt_payload(payload, [public_key])
        with pytest.raises(backup_core.BackupError, match="keine Daten verändert"):
            backup_core.restore_backup(session, invalid_backup, private_key, "test-admin")
        session.expire_all()
        assert sorted(session.scalars(select(models.Employee.name))) == ["Next Person", "Test Person"]
        assert session.scalar(select(models.Department.name)) == "Testabteilung"
