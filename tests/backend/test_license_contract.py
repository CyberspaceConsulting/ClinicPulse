"""Contract between Medora and the License Manager (see TEST.md)."""
import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest


def license_token(license_key, **extra) -> str:
    return jwt.encode(
        {
            "iss": "medora-licensing",
            "aud": "medora",
            "sub": "contract-customer",
            "jti": f"contract-{extra.get('federal_state', 'none')}-{extra.get('operational_profile', 'none')}",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
            "license_status": "PAID",
            **extra,
        },
        license_key,
        algorithm="RS256",
    )


def setup(client, token: str):
    return client.post("/api/setup", json={
        "username": "contract-admin", "first_name": "Contract", "last_name": "Administrator",
        "password": "secure-password-123", "license_token": token, "unit_name": "Leitstelle Test",
    })


def test_setup_needs_no_manual_location_fields_when_license_provides_them(client, license_key):
    token = license_token(license_key, federal_state="Hessen", operational_profile="care_facility",
                          institution_name="Pflegeheim Mitte")
    assert setup(client, token).status_code == 201
    config = client.get("/api/admin/business-configuration").json()
    assert config["federal_state"] == "Hessen" and config["federal_state_managed"] is True
    assert config["operational_profile"] == "care_facility" and config["operational_profile_managed"] is True
    assert client.get("/api/setup/status").json()["institution_name"] == "Pflegeheim Mitte"


@pytest.mark.parametrize("claims", [
    {"operational_profile": "hospital"},
    {"federal_state": "Bayern"},
    {},
])
def test_setup_fails_clearly_when_license_lacks_location_data(client, license_key, claims):
    response = setup(client, license_token(license_key, **claims))
    assert response.status_code == 422
    assert "License Manager" in response.json()["detail"]


@pytest.mark.parametrize("claims", [{"federal_state": "Atlantis"}, {"operational_profile": "castle"}])
def test_invalid_managed_claims_are_rejected(client, license_key, claims):
    assert setup(client, license_token(license_key, **claims)).status_code == 422


def test_managed_values_cannot_be_overridden_by_admin(client, license_key):
    token = license_token(license_key, federal_state="Sachsen", operational_profile="ils")
    assert setup(client, token).status_code == 201
    response = client.put("/api/admin/business-configuration", json={
        "federal_state": "Bayern", "operational_profile": "hospital", "sunday_work_authorized": True,
    })
    assert response.status_code == 200
    assert (response.json()["federal_state"], response.json()["operational_profile"]) == ("Sachsen", "ils")
    assert response.json()["sunday_work_authorized"] is True


def test_license_check_adopts_changed_values_from_manager(client, license_key, monkeypatch):
    token = license_token(license_key, federal_state="Sachsen", operational_profile="ils")
    assert setup(client, token).status_code == 201
    from app import license_manager

    original = license_manager.urllib.request.urlopen

    def changed(request, timeout):
        response = original(request, timeout)
        status = jwt.decode(response.payload["signed_status_token"], options={"verify_signature": False})
        status["federal_state"], status["operational_profile"] = "Berlin", "hospital"
        status["iat"], status["exp"] = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=48)
        response.payload = {"signed_status_token": jwt.encode(status, license_key, algorithm="RS256")}
        return response

    monkeypatch.setattr(license_manager.urllib.request, "urlopen", changed)
    assert client.post("/api/admin/license/check").status_code == 200
    config = client.get("/api/admin/business-configuration").json()
    assert (config["federal_state"], config["operational_profile"]) == ("Berlin", "hospital")
