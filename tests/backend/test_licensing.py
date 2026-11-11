import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from app.database import SessionLocal
from app.licensing import (
    generate_keypair,
    issue_license,
    validate_license_token,
)
from app.license_manager import license_is_read_only
from app import license_manager
from app.models import LicenseState


def test_issuer_creates_encrypted_keypair_and_valid_license(tmp_path: Path, monkeypatch):
    private_key_path = tmp_path / "issuer-private.pem"
    public_key_path = tmp_path / "issuer-public.pem"
    passphrase = "a-long-test-passphrase"
    generate_keypair(private_key_path, public_key_path, passphrase)

    assert private_key_path.stat().st_mode & 0o777 == 0o600
    assert b"ENCRYPTED" in private_key_path.read_bytes()

    now = datetime.now(timezone.utc)
    token = issue_license(
        private_key_path,
        "customer-001",
        "PAID",
        now + timedelta(days=30),
        None,
        passphrase,
    )
    monkeypatch.setenv("CLINICPULSE_LICENSE_PUBLIC_KEY_FILE", str(public_key_path))
    claims = validate_license_token(token)

    assert claims["sub"] == "customer-001"
    assert claims["license_status"] == "PAID"


def test_rejects_expired_grace_period(client, license_key):
    token = jwt.encode(
        {
            "iss": "clinicpulse-licensing",
            "aud": "clinicpulse",
            "sub": "test-customer",
            "jti": "expired-grace-license",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
            "license_status": "GRACE_PERIOD",
            "grace_until": (datetime.now(timezone.utc) - timedelta(days=1)).timestamp(),
        },
        license_key,
        algorithm="RS256",
    )
    response = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "first_name": "Test",
            "last_name": "Administrator",
            "password": "test-password-with-twelve",
            "license_token": token,
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Diese Lizenz ist gesperrt"


def test_cached_status_signature_and_offline_window(client):
    response = client.post(
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
    assert response.status_code == 201

    with SessionLocal() as db:
        state = db.get(LicenseState, 1)
        assert state is not None
        assert state.signed_status_token is not None
        assert state.last_successful_check_at is not None
        license_token = os.environ["TEST_LICENSE_TOKEN"]
        offline_at = state.last_successful_check_at + timedelta(days=6)
        assert license_is_read_only(
            state.signed_status_token,
            state.last_successful_check_at,
            offline_at,
            license_token,
            state.installation_id,
        ) == (False, None)

        parts = state.signed_status_token.split(".")
        parts[2] = ("A" if not parts[2].startswith("A") else "B") + parts[2][1:]
        assert license_is_read_only(
            ".".join(parts),
            state.last_successful_check_at,
            offline_at,
            license_token,
            state.installation_id,
        )[0]
        assert license_is_read_only(
            state.signed_status_token,
            state.last_successful_check_at,
            state.last_successful_check_at + timedelta(days=8),
            license_token,
            state.installation_id,
        )[0]


def test_overdue_status_is_valid_but_read_only(client, license_key):
    license_token = os.environ["TEST_LICENSE_TOKEN"]
    license_claims = license_manager.decode_license_claims(license_token)
    installation_id = "test-installation"
    nonce = "test-nonce"
    now = datetime.now(timezone.utc)
    status_token = jwt.encode(
        {
            "iss": "clinicpulse-licensing",
            "aud": "clinicpulse",
            "sub": license_claims["sub"],
            "jti": "overdue-status-id",
            "iat": now,
            "exp": now + timedelta(hours=48),
            "license_jti": license_claims["jti"],
            "installation_id": installation_id,
            "nonce": nonce,
            "license_status": "OVERDUE",
            "license_expires_at": license_claims["exp"],
            "checked_at": now.timestamp(),
            "vip": False,
            "suppress_warnings": False,
        },
        license_key,
        algorithm="RS256",
    )

    verified = license_manager._verify_status(
        status_token, license_claims, installation_id, nonce
    )
    assert verified.claims["license_status"] == "OVERDUE"
    assert license_manager.license_is_read_only(
        status_token,
        now,
        now,
        license_token,
        installation_id,
    ) == (True, "License is overdue")


def test_expired_license_token_is_still_sent_for_manager_status(client, license_key):
    token = jwt.encode(
        {
            "iss": "clinicpulse-licensing",
            "aud": "clinicpulse",
            "sub": "expired-customer",
            "jti": "expired-license",
            "iat": datetime.now(timezone.utc) - timedelta(days=60),
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "license_status": "PAID",
        },
        license_key,
        algorithm="RS256",
    )
    response = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "first_name": "Test",
            "last_name": "Administrator",
            "password": "test-password-with-twelve",
            "license_token": token,
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert response.status_code == 201


def test_status_response_must_match_request_nonce(client, license_key, monkeypatch):
    class FakeResponse:
        status = 200

        def __init__(self, token):
            self.token = token

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return json.dumps({"signed_status_token": self.token}).encode()

    def fake_urlopen(request, timeout):
        body = json.loads(request.data)
        license_claims = jwt.decode(
            body["license_token"],
            options={"verify_signature": False, "verify_exp": False},
        )
        now = datetime.now(timezone.utc)
        status_token = jwt.encode(
            {
                "iss": "clinicpulse-licensing",
                "aud": "clinicpulse",
                "sub": license_claims["sub"],
                "jti": "status-test-id",
                "iat": now,
                "exp": now + timedelta(hours=48),
                "license_jti": license_claims["jti"],
                "installation_id": body["installation_id"],
                "nonce": f'{body["nonce"]}-wrong',
                "license_status": "PAID",
                "license_expires_at": license_claims["exp"],
                "checked_at": now.timestamp(),
                "vip": False,
                "suppress_warnings": False,
            },
            license_key,
            algorithm="RS256",
        )
        return FakeResponse(status_token)

    monkeypatch.setattr(license_manager.urllib.request, "urlopen", fake_urlopen)
    response = client.post(
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
    assert response.status_code == 422


def test_license_check_retry_schedule():
    assert license_manager.check_retry_delay(1) == timedelta(minutes=15)
    assert license_manager.check_retry_delay(2) == timedelta(hours=1)
    assert license_manager.check_retry_delay(3) == timedelta(hours=6)
    assert license_manager.check_retry_delay(8) == timedelta(hours=6)
