import os
from datetime import datetime, timedelta, timezone
import json

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import pytest
from fastapi.testclient import TestClient

from app import license_manager
from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def license_key(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setenv("MEDORA_LICENSE_PUBLIC_KEY", public_key.decode())
    return private_key


@pytest.fixture
def valid_license_token(license_key):
    return jwt.encode(
        {
            "iss": "medora-licensing",
            "aud": "medora",
            "sub": "test-customer",
            "jti": "test-license-1",
            "institution_name": "Klinikum Beispiel",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
            "license_status": "PAID",
        },
        license_key,
        algorithm="RS256",
    )


@pytest.fixture
def blocked_license_token(license_key):
    return jwt.encode(
        {
            "iss": "medora-licensing",
            "aud": "medora",
            "sub": "test-customer",
            "jti": "blocked-license-1",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
            "license_status": "BLOCKED",
        },
        license_key,
        algorithm="RS256",
    )


@pytest.fixture
def client(valid_license_token, license_key, monkeypatch):
    monkeypatch.setenv("TEST_LICENSE_TOKEN", valid_license_token)
    monkeypatch.setenv("MEDORA_LICENSE_API_URL", "https://license.test/api/v1")

    class FakeResponse:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert request.full_url.startswith("https://license.test/api/v1/instances/")
        assert timeout == 8
        body = json.loads(request.data)
        license_claims = jwt.decode(
            body["license_token"],
            options={"verify_signature": False, "verify_exp": False},
        )
        now = datetime.now(timezone.utc)
        license_status = license_claims["license_status"]
        grace_until = license_claims.get("grace_until")
        if license_status == "GRACE_PERIOD" and grace_until is not None and grace_until <= now.timestamp():
            license_status = "BLOCKED"
        claims = {
            "iss": "medora-licensing",
            "aud": "medora",
            "sub": license_claims["sub"],
            "jti": "status-test-id",
            "iat": now,
            "exp": now + timedelta(hours=48),
            "license_jti": license_claims["jti"],
            "installation_id": body["installation_id"],
            "nonce": body["nonce"],
            "license_status": license_status,
            "license_expires_at": license_claims["exp"],
            "checked_at": now.timestamp(),
            "grace_until": grace_until,
            "vip": False,
            "suppress_warnings": False,
        }
        for managed_claim in ("institution_name", "operational_profile", "federal_state"):
            if managed_claim in license_claims:
                claims[managed_claim] = license_claims[managed_claim]
        token = jwt.encode(claims, license_key, algorithm="RS256")
        return FakeResponse({"signed_status_token": token})

    monkeypatch.setattr(license_manager.urllib.request, "urlopen", fake_urlopen)
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
