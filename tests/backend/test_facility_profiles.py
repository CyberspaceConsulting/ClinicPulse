import os

import pytest

from test_api import _login_headers


def _setup(client, profile, **extra):
    response = client.post("/api/setup", json={
        "username": "profile-admin", "first_name": "Profil", "last_name": "Administrator",
        "password": "secure-password-123", "license_token": os.environ["TEST_LICENSE_TOKEN"],
        "federal_state": "Bayern", "operational_profile": profile, **extra,
    })
    return response


def _admin(client):
    return _login_headers(client, "profile-admin", "secure-password-123")


def test_ils_setup_creates_main_control_center_and_keeps_a_single_unit(client):
    assert _setup(client, "ils").status_code == 422
    assert _setup(client, "ils", unit_name="Leitstelle Nord").status_code == 201
    admin = _admin(client)

    departments = client.get("/api/departments", headers=admin).json()
    assert [item["name"] for item in departments] == ["Leitstelle Nord"]
    catalog = client.get("/api/role-catalog", headers=admin).json()
    assert catalog["structure"]["single_unit"] is True and catalog["structure"]["uses_vehicles"] is False

    assert client.post("/api/departments", headers=admin, json={"name": "Zweite"}).status_code == 409
    assert client.delete(f"/api/departments/{departments[0]['id']}", headers=admin).status_code == 409
    renamed = client.put(f"/api/departments/{departments[0]['id']}", headers=admin, json={"name": "Leitstelle Süd"})
    assert renamed.status_code == 200
    assert client.post("/api/vehicles", headers=admin, json={
        "department_id": departments[0]["id"], "vehicle_type": "RTW", "name": "RTW 1",
    }).status_code == 409


def test_other_facility_requires_configuration_in_setup(client):
    assert _setup(client, "other").status_code == 422
    assert _setup(client, "other", unit_label="Bereich", unit_label_plural="Bereiche").status_code == 422
    response = _setup(
        client, "other", unit_label="Bereich", unit_label_plural="Bereiche", unit_gender="m",
        lead_label="Bereichsleitung", single_unit=False, uses_vehicles=True,
    )
    assert response.status_code == 201
    admin = _admin(client)
    config = client.get("/api/admin/business-configuration", headers=admin).json()
    assert (config["unit_label"], config["unit_label_plural"], config["unit_gender"], config["lead_label"]) == (
        "Bereich", "Bereiche", "m", "Bereichsleitung",
    )
    assert config["single_unit"] is False and config["uses_vehicles"] is True
    catalog = client.get("/api/role-catalog", headers=admin).json()
    assert {role["key"]: role["label"] for role in catalog["access_roles"]}["HOSPITAL_MANAGEMENT"] == "Bereichsleitung"
    assert catalog["structure"]["unit_label"] == "Bereich"

    updated = client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Bayern", "unit_label": "Team", "unit_label_plural": "Teams", "unit_gender": "n",
        "uses_vehicles": False,
    })
    assert updated.status_code == 200
    assert (updated.json()["unit_label"], updated.json()["uses_vehicles"]) == ("Team", False)


def test_other_facility_with_single_unit_needs_a_unit_name(client):
    base = dict(unit_label="Zentrale", unit_label_plural="Zentralen", unit_gender="f", lead_label="Leitung", single_unit=True)
    assert _setup(client, "other", **base).status_code == 422
    assert _setup(client, "other", unit_name="Zentrale Mitte", **base).status_code == 201
    admin = _admin(client)
    assert [item["name"] for item in client.get("/api/departments", headers=admin).json()] == ["Zentrale Mitte"]
    assert client.post("/api/departments", headers=admin, json={"name": "Noch eine"}).status_code == 409


@pytest.mark.parametrize("profile", ["hospital", "care_facility"])
def test_hospital_like_profiles_have_departments_but_no_vehicles(client, profile):
    assert _setup(client, profile).status_code == 201
    admin = _admin(client)
    structure = client.get("/api/role-catalog", headers=admin).json()["structure"]
    assert structure["single_unit"] is False and structure["uses_vehicles"] is False
    department = client.post("/api/departments", headers=admin, json={"name": "Station"}).json()
    assert client.post("/api/departments", headers=admin, json={"name": "Station 2"}).status_code == 201
    assert client.post("/api/vehicles", headers=admin, json={
        "department_id": department["id"], "vehicle_type": "RTW", "name": "RTW 1",
    }).status_code == 409
    # Terminology settings cannot be changed for fixed facility types.
    changed = client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Bayern", "unit_label": "Fantasie", "unit_label_plural": "Fantasien", "unit_gender": "f",
    }).json()
    assert changed["unit_label"] is None


def _rescue_setup(client):
    assert _setup(client, "rescue_service").status_code == 201
    admin = _admin(client)
    station = client.post("/api/departments", headers=admin, json={"name": "Wache Nord"}).json()["id"]
    other = client.post("/api/departments", headers=admin, json={"name": "Wache Süd"}).json()["id"]
    planner_employee = client.post("/api/employees", headers=admin, json={
        "first_name": "Wach", "last_name": "Planer", "role": "Notarzt", "department_id": station,
    }).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Wach", "last_name": "Planer", "username": "wache-planer", "password": "wache-planer-12345",
        "role_key": "EMPLOYEE", "department_id": station, "employee_id": planner_employee,
        "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    planner = _login_headers(client, "wache-planer", "wache-planer-12345")
    return admin, planner, station, other


def test_vehicles_belong_to_a_location_and_shifts_use_them(client):
    admin, planner, station, other = _rescue_setup(client)
    rtw = client.post("/api/vehicles", headers=planner, json={
        "department_id": station, "vehicle_type": "RTW", "name": "RTW 1/83-1",
    })
    assert rtw.status_code == 201 and rtw.json()["is_active"] is True
    vehicle_id = rtw.json()["id"]
    assert client.post("/api/vehicles", headers=planner, json={
        "department_id": station, "vehicle_type": "RTW", "name": "RTW 1/83-1",
    }).status_code == 409
    # A planner of one location cannot create vehicles for another.
    assert client.post("/api/vehicles", headers=planner, json={
        "department_id": other, "vehicle_type": "KTW", "name": "KTW 1",
    }).status_code == 403
    assert [item["name"] for item in client.get("/api/vehicles", headers=planner).json()] == ["RTW 1/83-1"]
    assert len(client.get("/api/vehicles", headers=admin).json()) == 1

    foreign_vehicle = client.post("/api/vehicles", headers=admin, json={
        "department_id": other, "vehicle_type": "NEF", "name": "NEF Süd",
    }).json()["id"]
    wrong = client.post("/api/shift-types", headers=planner, json={
        "name": "NEF Früh", "start_time": "07:00:00", "end_time": "13:00:00", "department_id": station,
        "vehicle_id": foreign_vehicle, "position": "Notarzt",
    })
    assert wrong.status_code == 409
    shift = client.post("/api/shift-types", headers=planner, json={
        "name": "RTW 1 Früh", "start_time": "07:00:00", "end_time": "13:00:00", "department_id": station,
        "vehicle_id": vehicle_id,
        "staffing_requirements": [
            {"position": "Notfallsanitäter", "required_staff": 1},
            {"position": "Rettungssanitäter", "required_staff": 1},
        ],
    })
    assert shift.status_code == 201 and shift.json()["vehicle_id"] == vehicle_id
    assert client.delete(f"/api/vehicles/{vehicle_id}", headers=planner).status_code == 409
    assert client.delete(f"/api/departments/{station}", headers=admin).status_code == 409


def test_deactivated_vehicle_is_not_planned(client):
    admin, planner, station, _other = _rescue_setup(client)
    vehicle = client.post("/api/vehicles", headers=planner, json={
        "department_id": station, "vehicle_type": "KTW", "name": "KTW 2",
    }).json()
    shift = client.post("/api/shift-types", headers=planner, json={
        "name": "KTW 2 Tag", "start_time": "08:00:00", "end_time": "14:00:00", "department_id": station,
        "vehicle_id": vehicle["id"], "position": "Rettungssanitäter",
    }).json()["id"]
    medic = client.post("/api/employees", headers=admin, json={
        "first_name": "Rita", "last_name": "Sanitäter", "role": "Rettungssanitäter", "department_id": station,
    }).json()["id"]

    active = client.post("/api/optimization/preview", headers=planner, json={
        "target_date": "2031-02-05", "department_id": station,
    }).json()
    assert [item["employee_id"] for item in active["suggestions"]] == [medic]

    off = client.put(f"/api/vehicles/{vehicle['id']}", headers=planner, json={
        "department_id": station, "vehicle_type": "KTW", "name": "KTW 2", "is_active": False,
    })
    assert off.status_code == 200 and off.json()["is_active"] is False
    inactive = client.post("/api/optimization/preview", headers=planner, json={
        "target_date": "2031-02-05", "department_id": station,
    }).json()
    assert inactive["suggestions"] == [] and inactive["unfilled_slots"] == []
    blocked = client.post("/api/assignments", headers=planner, json={
        "employee_id": medic, "shift_type_id": shift,
        "starts_at": "2031-02-05T08:00:00+00:00", "ends_at": "2031-02-05T14:00:00+00:00",
    })
    assert blocked.status_code == 409 and "deactivated" in blocked.json()["detail"]

    on = client.put(f"/api/vehicles/{vehicle['id']}", headers=planner, json={
        "department_id": station, "vehicle_type": "KTW", "name": "KTW 2", "is_active": True,
    })
    assert on.status_code == 200
    assert client.post("/api/assignments", headers=planner, json={
        "employee_id": medic, "shift_type_id": shift,
        "starts_at": "2031-02-05T08:00:00+00:00", "ends_at": "2031-02-05T14:00:00+00:00",
    }).status_code == 201
