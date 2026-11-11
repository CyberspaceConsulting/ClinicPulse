import os

from sqlalchemy import select

from app.database import SessionLocal
from app.main import login_throttle
from app.models import LoginAttempt


def test_login_throttle_persists_and_clears_failures(client):
    client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "first_name": "Test",
            "last_name": "Administrator",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    ip = "192.0.2.15"
    username = "CaseSensitiveUser"
    secret = "shared-installation-signing-key"
    now = 1_800_000_000.0

    with SessionLocal() as db:
        assert [
            login_throttle.record_failure(db, ip, username, secret, now + index)
            for index in range(5)
        ] == [0.5, 1, 2, 4, 8]
        assert login_throttle.retry_after(db, ip, username, secret, now + 5) == 59
        stored = db.scalar(select(LoginAttempt))
        assert stored is not None
        assert len(stored.key) == 64
        assert ip not in stored.key
        assert username not in stored.key

    with SessionLocal() as db:
        assert login_throttle.retry_after(db, ip, username, secret, now + 5) == 59
        login_throttle.record_success(db, ip, username, secret)
        assert login_throttle.retry_after(db, ip, username, secret, now + 5) == 0


def test_login_throttle_escalates_and_resets_expired_window(client):
    client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "first_name": "Test",
            "last_name": "Administrator",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    now = 1_800_000_100.0
    with SessionLocal() as db:
        for index in range(10):
            login_throttle.record_failure(
                db,
                "192.0.2.16",
                "another-user",
                "shared-installation-signing-key",
                now + index,
            )
        assert login_throttle.retry_after(
            db,
            "192.0.2.16",
            "another-user",
            "shared-installation-signing-key",
            now + 10,
        ) == 899
        login_throttle.record_failure(
            db,
            "192.0.2.16",
            "another-user",
            "shared-installation-signing-key",
            now + 10 + 15 * 60,
        )
        assert login_throttle.retry_after(
            db,
            "192.0.2.16",
            "another-user",
            "shared-installation-signing-key",
            now + 10 + 15 * 60,
        ) == 0
