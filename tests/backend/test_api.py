import os
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from app import main
from sqlalchemy import inspect


def auth_header(client):
    setup = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert setup.status_code == 201
    assert "access_token" not in setup.json()
    assert "HttpOnly" in setup.headers["set-cookie"]
    access_token = client.cookies.get("clinicpulse_session")
    assert access_token
    response = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}


def test_planning_requires_authentication(client):
    assert client.get("/api/setup/status").json() == {
        "setup_required": True,
        "institution_name": None,
    }
    assert client.get("/api/employees").status_code == 401
    assert client.get("/api/health").status_code == 200
    missing_license_token = client.post(
        "/api/setup",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    )
    assert missing_license_token.status_code == 422
    missing_business_configuration = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
        },
    )
    assert missing_business_configuration.status_code == 422
    blank_license_token = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": "   ",
        },
    )
    assert blank_license_token.status_code == 422


def test_new_accounts_accept_eight_character_passwords(client):
    setup = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "C0mp!ex8",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert setup.status_code == 201
    admin = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    accepted = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "eight-char-user",
            "password": "C0mp!ex8",
            "role_key": "KIOSK",
            "can_view": True,
        },
    )
    assert accepted.status_code == 201
    rejected = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "seven-char-user",
            "password": "Short7!",
            "role_key": "KIOSK",
            "can_view": True,
        },
    )
    assert rejected.status_code == 422


def test_account_username_is_stored_as_ciphertext_and_remains_authenticatable(client):
    setup = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert setup.status_code == 201
    with main.engine.connect() as connection:
        stored_username = connection.exec_driver_sql(
            "SELECT username FROM admin_account"
        ).scalar_one()
    assert stored_username != "test-admin"
    login = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    )
    assert login.status_code == 200


def test_institution_name_from_signed_license_is_shown_on_login(client):
    setup = client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert setup.status_code == 201
    assert client.get("/api/setup/status").json() == {
        "setup_required": False,
        "institution_name": "Klinikum Beispiel",
    }
    status_response = client.get("/api/license/status")
    assert status_response.status_code == 200
    assert status_response.json()["institution_name"] == "Klinikum Beispiel"


def test_initial_setup_requires_valid_signed_license(
    client, blocked_license_token, monkeypatch, caplog
):
    setup_data = {
        "username": "test-admin",
        "password": "test-password-with-twelve",
        "license_token": "not-a-signed-license",
        "federal_state": "Nordrhein-Westfalen",
        "operational_profile": "hospital",
    }
    invalid = client.post("/api/setup", json=setup_data)
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "Lizenz-Token oder signierter Lizenzstatus ist ungültig"
    assert "Initial license activation rejected: License signature or claims are invalid" in caplog.text

    setup_data["license_token"] = blocked_license_token
    blocked = client.post("/api/setup", json=setup_data)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Diese Lizenz ist gesperrt"

    monkeypatch.delenv("CLINICPULSE_LICENSE_PUBLIC_KEY")
    monkeypatch.setenv("CLINICPULSE_LICENSE_PUBLIC_KEY_FILE", "/missing/license-public.pem")
    unconfigured = client.post("/api/setup", json=setup_data)
    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"] == "Lizenzprüfung ist nicht konfiguriert"

    monkeypatch.setenv("CLINICPULSE_LICENSE_PUBLIC_KEY", "not a PEM public key")
    misconfigured = client.post("/api/setup", json=setup_data)
    assert misconfigured.status_code == 503


def test_create_and_list_staff_shifts_and_assignments(client):
    admin_headers = auth_header(client)
    department_response = client.post("/api/departments", json={"name": "General"}, headers=admin_headers)
    department_id = department_response.json()["id"]
    employee_response = client.post(
        "/api/employees",
        json={"first_name": "Alex", "last_name": "Beispiel", "role": "Nurse", "department_id": department_id},
        headers=admin_headers,
    )
    assert employee_response.status_code == 201
    employee_id = employee_response.json()["id"]
    second_employee_response = client.post(
        "/api/employees",
        json={"first_name": "Sam", "last_name": "Beispiel", "role": "Nurse", "department_id": department_id},
        headers=admin_headers,
    )
    second_employee_id = second_employee_response.json()["id"]
    planner_response = client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "planner",
            "password": "planner-password-1234",
            "role_key": "OBERARZT",
            "department_id": department_id,
            "can_edit": True,
            "can_approve": True,
        },
    )
    assert planner_response.status_code == 201
    client.post("/api/auth/login", json={"username": "planner", "password": "planner-password-1234"})
    headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    shift_response = client.post(
        "/api/shift-types",
        json={
            "name": "Early",
            "start_time": "07:00:00",
            "end_time": "15:00:00",
            "color": "#2563eb",
            "position": "Nurse",
            "required_staff": 2,
            "department_id": department_id,
        },
        headers=headers,
    )
    assert shift_response.status_code == 201
    shift_id = shift_response.json()["id"]

    assignment_response = client.post(
        "/api/assignments",
        json={
            "employee_id": employee_id,
            "shift_type_id": shift_id,
            "starts_at": "2026-10-14T07:00:00+02:00",
            "ends_at": "2026-10-14T15:00:00+02:00",
        },
        headers=headers,
    )
    assert assignment_response.status_code == 201
    assert assignment_response.json()["employee_name"] == "Alex Beispiel"
    assert assignment_response.json()["shift_name"] == "Early"

    listed = client.get("/api/assignments?from=2026-10-14&to=2026-10-14", headers=headers)
    assert len(listed.json()) == 1
    assert listed.json()[0]["shift_name"] == "Early"

    suggestions = client.get(
        "/api/smart-selection?shift_type_id="
        f"{shift_id}&starts_at=2026-10-14T07%3A00%3A00%2B02%3A00"
        "&ends_at=2026-10-14T15%3A00%3A00%2B02%3A00",
        headers=headers,
    )
    assert suggestions.status_code == 200
    assert [candidate["employee_id"] for candidate in suggestions.json()["candidates"]] == [second_employee_id]
    approved = client.post(
        "/api/smart-selection/approve",
        headers=headers,
        json={
            "employee_id": second_employee_id,
            "shift_type_id": shift_id,
            "starts_at": "2026-10-14T07:00:00+02:00",
            "ends_at": "2026-10-14T15:00:00+02:00",
        },
    )
    assert approved.status_code == 201

    overlapping = client.post(
        "/api/assignments",
        json={
            "employee_id": employee_id,
            "shift_type_id": shift_id,
            "starts_at": "2026-10-14T14:00:00+02:00",
            "ends_at": "2026-10-14T22:00:00+02:00",
        },
        headers=headers,
    )
    assert overlapping.status_code == 409


def test_optimizer_returns_a_non_persisted_role_aware_day_draft(client):
    admin = auth_header(client)
    department_id = client.post(
        "/api/departments", json={"name": "Optimization"}, headers=admin
    ).json()["id"]
    nurse = client.post("/api/employees", headers=admin, json={
        "first_name": "Nora", "last_name": "Nurse", "role": "Nurse", "department_id": department_id,
    }).json()["id"]
    other = client.post("/api/employees", headers=admin, json={
        "first_name": "Alex", "last_name": "Other", "role": "Assistant", "department_id": department_id,
    }).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "optimizer", "password": "optimizer-password-123",
        "role_key": "OBERARZT", "department_id": department_id,
        "can_view": True, "can_edit": True,
    }).status_code == 201
    planner = _login_headers(client, "optimizer", "optimizer-password-123")
    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Day shift", "start_time": "07:00:00", "end_time": "15:30:00",
        "position": "Nurse", "required_staff": 2, "department_id": department_id,
    }).json()["id"]

    preview = client.post("/api/optimization/preview", headers=planner, json={
        "target_date": "2031-02-04", "department_id": department_id,
    })

    assert preview.status_code == 200
    result = preview.json()
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert {item["employee_id"] for item in result["suggestions"]} == {nurse, other}
    assert sum(item["role_match"] for item in result["suggestions"]) == 1
    assert result["unfilled_slots"] == []
    assert client.get(
        "/api/assignments?from=2031-02-04&to=2031-02-04", headers=planner
    ).json() == []

    absence = client.post("/api/absences", headers=planner, json={
        "employee_id": nurse,
        "kind": "vacation",
        "start_date": "2031-02-04",
        "end_date": "2031-02-04",
    })
    assert absence.status_code == 201
    with_absence = client.post("/api/optimization/preview", headers=planner, json={
        "target_date": "2031-02-04", "department_id": department_id,
    })
    assert {item["employee_id"] for item in with_absence.json()["suggestions"]} == {other}
    assert len(with_absence.json()["unfilled_slots"]) == 1

    forbidden = client.post("/api/optimization/preview", headers=admin, json={
        "target_date": "2031-02-04", "department_id": department_id,
    })
    assert forbidden.status_code == 403


def test_planning_period_only_fills_gaps_and_approves_atomically(client):
    admin = auth_header(client)
    department_id = client.post(
        "/api/departments", json={"name": "Planning"}, headers=admin
    ).json()["id"]
    employees = [
        client.post("/api/employees", headers=admin, json={
            "first_name": f"Planner Nurse {index}", "last_name": "Test", "role": "Nurse", "department_id": department_id,
        }).json()["id"]
        for index in range(3)
    ]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "period-planner", "password": "period-password-123",
        "role_key": "OBERARZT", "department_id": department_id,
        "can_view": True, "can_edit": True,
    }).status_code == 201
    planner = _login_headers(client, "period-planner", "period-password-123")
    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Day", "start_time": "08:00:00", "end_time": "14:00:00",
        "position": "Nurse", "required_staff": 2, "department_id": department_id,
    }).json()["id"]
    fixed = client.post("/api/assignments", headers=planner, json={
        "employee_id": employees[0], "shift_type_id": shift_id,
        "starts_at": "2031-02-05T07:00:00Z", "ends_at": "2031-02-05T13:00:00Z",
    })
    assert fixed.status_code == 201

    preview = client.post("/api/planning/preview", headers=planner, json={
        "start_date": "2031-02-03", "end_date": "2031-02-07", "department_id": department_id,
    })

    assert preview.status_code == 200
    days = {day["target_date"]: day for day in preview.json()["days"]}
    assert len(days) == 5
    assert [item["employee_id"] for item in days["2031-02-05"]["suggestions"]].count(employees[0]) == 0
    assert len(days["2031-02-05"]["suggestions"]) == 1
    assert len(days["2031-02-04"]["suggestions"]) == 2
    assert client.get(
        "/api/assignments?from=2031-02-03&to=2031-02-07", headers=planner
    ).json().__len__() == 1

    items = [
        {"employee_id": item["employee_id"], "shift_type_id": item["shift_type_id"], "target_date": day["target_date"]}
        for day in days.values() for item in day["suggestions"]
    ]
    approved = client.post("/api/planning/approve", headers=planner, json={"items": items})
    assert approved.status_code == 201
    assert approved.json()["created"] == len(items)
    stored = client.get("/api/assignments?from=2031-02-03&to=2031-02-07", headers=planner).json()
    assert len(stored) == len(items) + 1

    repeated = client.post("/api/planning/approve", headers=planner, json={"items": items})
    assert repeated.status_code == 409
    assert len(client.get(
        "/api/assignments?from=2031-02-03&to=2031-02-07", headers=planner
    ).json()) == len(stored)
    assert client.post("/api/planning/preview", headers=admin, json={
        "start_date": "2031-02-03", "end_date": "2031-02-07",
    }).status_code == 403


def test_setup_is_one_time_and_password_change_revokes_old_token(client):
    headers = auth_header(client)
    duplicate_setup = client.post(
        "/api/setup",
        json={
            "username": "another-admin",
            "password": "another-password-123",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    assert duplicate_setup.status_code == 409

    changed = client.put(
        "/api/settings/account",
        headers=headers,
        json={
            "current_password": "test-password-with-twelve",
            "username": "clinic-admin",
            "new_password": "new-password-for-admin-123",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["username"] == "clinic-admin"
    assert client.get("/api/employees", headers=headers).status_code == 401
    assert client.get("/api/employees").status_code == 200
    assert client.post(
        "/api/auth/login",
        json={"username": "clinic-admin", "password": "new-password-for-admin-123"},
    ).status_code == 200


def test_login_failures_are_delayed_and_temporarily_throttled(client, monkeypatch):
    monkeypatch.setattr(main.time_module, "sleep", lambda _: None)
    auth_header(client)
    delays = []
    monkeypatch.setattr(main.time_module, "sleep", delays.append)
    credentials = {"username": "test-admin", "password": "incorrect-password"}

    for _ in range(5):
        response = client.post("/api/auth/login", json=credentials)
        assert response.status_code == 401

    assert delays == [0.5, 1, 2, 4, 8]
    blocked = client.post("/api/auth/login", json=credentials)
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"


def test_successful_login_clears_failed_attempts(client, monkeypatch):
    monkeypatch.setattr(main.time_module, "sleep", lambda _: None)
    auth_header(client)
    credentials = {"username": "test-admin", "password": "incorrect-password"}
    for _ in range(4):
        assert client.post("/api/auth/login", json=credentials).status_code == 401

    valid = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    )
    assert valid.status_code == 200
    assert client.post("/api/auth/login", json=credentials).status_code == 401


def test_admin_can_review_audit_events_without_sensitive_payloads(client, monkeypatch):
    monkeypatch.setattr(main.time_module, "sleep", lambda _: None)
    assert client.get("/api/admin/audit").status_code == 401

    client.post(
        "/api/setup",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "license_token": os.environ["TEST_LICENSE_TOKEN"],
            "federal_state": "Nordrhein-Westfalen",
            "operational_profile": "hospital",
        },
    )
    response = client.post(
        "/api/departments",
        json={"name": "Audit Clinic"},
    )
    assert response.status_code == 201
    failed_login = client.post(
        "/api/auth/login",
        json={"username": "private-guessed-name", "password": "private-guessed-password"},
    )
    assert failed_login.status_code == 401

    audit_response = client.get("/api/admin/audit?limit=100")
    assert audit_response.status_code == 200
    events = audit_response.json()["items"]
    assert any(
        event["action"] == "created"
        and event["entity_type"] == "Department"
        and event["actor_username"] == "test-admin"
        for event in events
    )
    failed = next(event for event in events if event["action"] == "login_failed")
    assert failed["actor_username"] == "anonymous"
    serialized = str(events)
    assert "private-guessed-name" not in serialized
    assert "private-guessed-password" not in serialized
    assert "license_token" not in serialized
    assert set(events[0]) == {
        "id",
        "created_at",
        "actor_username",
        "action",
        "entity_type",
        "entity_id",
    }
    first_page = client.get("/api/admin/audit?limit=1")
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 1
    assert first_page.json()["limit"] == 1

    department_id = response.json()["id"]
    created_user = client.post(
        "/api/users",
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "audit-kiosk",
            "password": "kiosk-password-1234",
            "role_key": "KIOSK",
            "department_id": department_id,
            "can_view": True,
        },
    )
    assert created_user.status_code == 201
    client.post("/api/auth/logout")
    kiosk_login = client.post(
        "/api/auth/login",
        json={"username": "audit-kiosk", "password": "kiosk-password-1234"},
    )
    assert kiosk_login.status_code == 200
    assert client.get("/api/admin/audit").status_code == 403


def test_update_check_is_admin_only_and_returns_version_info(client, monkeypatch):
    auth_header(client)
    monkeypatch.setattr(
        main.update_checker,
        "check",
        lambda channel="stable", force=False: {
            "current_version": "0.1.0",
            "channel": channel,
            "latest_version": "0.2.0",
            "update_available": True,
            "status": "update_available",
            "message": "Version 0.2.0 ist verfügbar.",
            "release_url": "https://github.com/CyberspaceConsulting/ClinicPulse/releases/tag/v0.2.0",
            "repository_url": "https://github.com/CyberspaceConsulting/ClinicPulse",
            "checked_at": "2026-10-13T00:00:00+00:00",
        },
    )
    response = client.get("/api/admin/updates")
    assert response.status_code == 200
    assert response.json()["update_available"] is True
    assert response.json()["latest_version"] == "0.2.0"

    client.cookies.clear()
    assert client.get("/api/admin/updates").status_code == 401


def test_admin_can_choose_update_channel(client, monkeypatch):
    auth_header(client)
    requested_channels = []

    def check(channel="stable", force=False):
        requested_channels.append((channel, force))
        return {"status": "no_release"}

    monkeypatch.setattr(main.update_checker, "check", check)
    changed = client.put("/api/admin/update-channel", json={"channel": "nightly"})
    assert changed.status_code == 200
    assert changed.json()["channel"] == "nightly"
    status_response = client.get("/api/admin/updates")
    assert status_response.status_code == 200
    assert requested_channels == [("nightly", True), ("nightly", False)]


def test_admin_cannot_stay_signed_in_but_department_user_can(client, monkeypatch):
    monkeypatch.setattr(main.time_module, "sleep", lambda _: None)
    auth_header(client)
    denied = client.post(
        "/api/auth/login",
        json={
            "username": "test-admin",
            "password": "test-password-with-twelve",
            "stay_signed_in": True,
        },
    )
    assert denied.status_code == 403
    assert "nicht verfügbar" in denied.json()["detail"]

    department = client.post("/api/departments", json={"name": "Kardiologie"})
    department_id = department.json()["id"]
    created = client.post(
        "/api/users",
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "planner",
            "password": "planner-password-1234",
            "role_key": "OBERARZT",
            "department_id": department_id,
            "can_view": True,
            "can_edit": True,
            "can_approve": True,
        },
    )
    assert created.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={
            "username": "planner",
            "password": "planner-password-1234",
            "stay_signed_in": True,
        },
    )
    assert login.status_code == 200
    assert login.json()["remember_me"] is True
    assert "Max-Age=2592000" in login.headers["set-cookie"]


def test_browser_sessions_expire_after_idle_but_kiosk_sessions_do_not(client):
    admin = auth_header(client)
    from app.security import get_account
    from app.database import SessionLocal

    with SessionLocal() as db:
        signing_key = get_account(db).signing_key
    stale_cookie = jwt.encode(
        {
            "sub": "a:1",
            "ver": 0,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "last_activity": (datetime.now(timezone.utc) - timedelta(minutes=31)).timestamp(),
            "remember_me": False,
        },
        signing_key,
        algorithm="HS256",
    )
    client.cookies.set("clinicpulse_session", stale_cookie)
    assert client.get("/api/departments").status_code == 401
    client.cookies.clear()

    fresh_login = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    )
    assert fresh_login.status_code == 200
    activity_response = client.get("/api/departments")
    assert activity_response.status_code == 200
    assert "clinicpulse_session=" in activity_response.headers["set-cookie"]


def test_kiosk_session_does_not_use_inactivity_opt_out_checkbox(client, monkeypatch):
    monkeypatch.setattr(main.time_module, "sleep", lambda _: None)
    admin = auth_header(client)
    department = client.post("/api/departments", json={"name": "ZNA"}, headers=admin)
    kiosk = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "lobby-kiosk",
            "password": "kiosk-password-1234",
            "role_key": "KIOSK",
            "department_id": department.json()["id"],
            "can_view": True,
            "can_edit": False,
            "can_approve": False,
        },
    )
    assert kiosk.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": "lobby-kiosk", "password": "kiosk-password-1234"},
    )
    assert login.status_code == 200
    assert login.json()["remember_me"] is True
    assert "Max-Age=2592000" in login.headers["set-cookie"]
    from app.database import SessionLocal
    from app.models import UserAccount
    from app.security import get_account

    with SessionLocal() as db:
        root = get_account(db)
        kiosk_user = db.query(UserAccount).filter_by(username="lobby-kiosk").one()
        kiosk_cookie = jwt.encode(
            {
                "sub": f"u:{kiosk_user.id}",
                "ver": kiosk_user.token_version,
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "last_activity": (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp(),
                "remember_me": True,
            },
            root.signing_key,
            algorithm="HS256",
        )
    client.cookies.set("clinicpulse_session", kiosk_cookie)
    assert client.get("/api/departments").status_code == 200


def test_profile_photo_privacy_is_limited_to_own_department(client):
    admin = auth_header(client)
    department = client.post("/api/departments", json={"name": "Neurologie"}, headers=admin)
    department_id = department.json()["id"]
    for username in ("planner-a", "planner-b"):
        created = client.post(
            "/api/users",
            headers=admin,
            json={
                "first_name": "Test", "last_name": "Nutzer", "username": username,
                "password": "planner-password-1234",
                "role_key": "OBERARZT",
                "department_id": department_id,
                "can_view": True,
                "can_edit": False,
                "can_approve": False,
            },
        )
        assert created.status_code == 201

    client.post(
        "/api/auth/login",
        json={"username": "planner-a", "password": "planner-password-1234"},
    )
    image_data = "data:image/png;base64,iVBORw0KGgo="
    saved = client.put(
        "/api/profile/me",
        json={"profile_image_data": image_data, "profile_photo_visibility": "department"},
    )
    assert saved.status_code == 200
    assert saved.json()["profile_image_data"] == image_data
    assert [item["username"] for item in client.get("/api/profile/department").json()] == []

    client.post(
        "/api/auth/login",
        json={"username": "planner-b", "password": "planner-password-1234"},
    )
    own_profile = client.put(
        "/api/profile/me",
        json={"profile_image_data": image_data, "profile_photo_visibility": "department"},
    )
    assert own_profile.status_code == 200
    client.post(
        "/api/auth/login",
        json={"username": "planner-a", "password": "planner-password-1234"},
    )
    shared = client.get("/api/profile/department")
    assert shared.status_code == 200
    assert [item["username"] for item in shared.json()] == ["planner-b"]


def test_department_scope_and_planner_permissions(client):
    admin = auth_header(client)
    department = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin)
    assert department.status_code == 201
    department_id = department.json()["id"]
    user = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "oberarzt",
            "password": "secure-password-123",
            "role_key": "OBERARZT",
            "department_id": department_id,
            "can_view": True,
            "can_edit": True,
            "can_approve": False,
        },
    )
    assert user.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": "oberarzt", "password": "secure-password-123"},
    )
    assert login.status_code == 200
    planner_cookie = client.cookies.get("clinicpulse_session")
    planner_headers = {"Authorization": f"Bearer {planner_cookie}"}

    shift = client.post(
        "/api/shift-types",
        headers=planner_headers,
        json={
            "name": "Chirurgie Früh",
            "start_time": "07:00:00",
            "end_time": "15:00:00",
            "position": "Chirurg",
            "required_staff": 1,
        },
    )
    assert shift.status_code == 201
    assert shift.json()["department_id"] == department_id

    chief = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "chefarzt",
            "password": "secure-chief-pass-123",
            "role_key": "CHEFARZT",
            "department_id": department_id,
        },
    )
    assert chief.status_code == 201
    client.post(
        "/api/auth/login",
        json={"username": "chefarzt", "password": "secure-chief-pass-123"},
    )
    chief_headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    assert len(client.get("/api/shift-types", headers=chief_headers).json()) == 1
    assert client.post(
        "/api/shift-types",
        headers=chief_headers,
        json={
            "name": "Not allowed",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "position": "Chirurg",
        },
    ).status_code == 403

    read_only_planner = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "planner-viewer",
            "password": "viewer-password-1234",
            "role_key": "OBERARZT",
            "department_id": department_id,
            "can_view": True,
            "can_edit": False,
            "can_approve": False,
        },
    )
    assert read_only_planner.status_code == 201
    client.post(
        "/api/auth/login",
        json={"username": "planner-viewer", "password": "viewer-password-1234"},
    )
    viewer_headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    assert client.get("/api/shift-types", headers=viewer_headers).status_code == 200
    assert client.post(
        "/api/shift-types",
        headers=viewer_headers,
        json={"name": "Viewer forbidden", "start_time": "07:00:00", "end_time": "15:00:00"},
    ).status_code == 403

    other_department = client.post(
        "/api/departments",
        headers=admin,
        json={"name": "Radiologie"},
    )
    other_department_id = other_department.json()["id"]
    other_planner = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "radiology-planner",
            "password": "radiology-password-123",
            "role_key": "OBERARZT",
            "department_id": other_department_id,
            "can_view": True,
            "can_edit": True,
        },
    )
    assert other_planner.status_code == 201
    client.post(
        "/api/auth/login",
        json={"username": "radiology-planner", "password": "radiology-password-123"},
    )
    radiology_headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    other_shift = client.post(
        "/api/shift-types",
        headers=radiology_headers,
        json={
            "name": "Radiology Day",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "position": "Radiologist",
        },
    )
    assert other_shift.status_code == 201
    cross_department_delete = client.delete(
        f"/api/shift-types/{other_shift.json()['id']}", headers=planner_headers,
    )
    assert cross_department_delete.status_code == 404
    assert [item["id"] for item in client.get("/api/shift-types", headers=radiology_headers).json()] == [
        other_shift.json()["id"]
    ]
    client.post(
        "/api/auth/login",
        json={"username": "chefarzt", "password": "secure-chief-pass-123"},
    )
    chief_headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    visible_shifts = client.get("/api/shift-types", headers=chief_headers)
    assert [shift["name"] for shift in visible_shifts.json()] == ["Chirurgie Früh"]


def test_department_planner_cannot_read_or_plan_for_another_department(client):
    admin = auth_header(client)
    departments = {
        name: client.post("/api/departments", headers=admin, json={"name": name}).json()["id"]
        for name in ("Chirurgie", "Radiologie")
    }
    employees = {}
    shifts = {}
    for name, department_id in departments.items():
        employees[name] = client.post("/api/employees", headers=admin, json={
            "first_name": name, "last_name": "Mitarbeiter", "role": "Pflege",
            "department_id": department_id,
        }).json()["id"]
        planner_username = "surgery-planner" if name == "Chirurgie" else "radiology-planner"
        planner_password = f"{planner_username}-password"
        planner = client.post("/api/users", headers=admin, json={
            "first_name": name, "last_name": "Planer", "username": planner_username,
            "password": planner_password, "role_key": "OBERARZT",
            "department_id": department_id, "can_view": True, "can_edit": True,
            "can_approve": True,
        })
        assert planner.status_code == 201
        planner_headers = _login_headers(client, planner_username, planner_password)
        shifts[name] = client.post("/api/shift-types", headers=planner_headers, json={
            "name": f"{name} Früh", "start_time": "08:00:00", "end_time": "16:00:00",
            "department_id": department_id,
        }).json()["id"]
        assignment = client.post("/api/assignments", headers=planner_headers, json={
            "employee_id": employees[name],
            "shift_type_id": shifts[name],
            "starts_at": "2031-02-05T07:00:00+00:00",
            "ends_at": "2031-02-05T15:00:00+00:00",
        })
        assert assignment.status_code == 201

    other_employee_account = client.post("/api/users", headers=admin, json={
        "first_name": "Radiologie", "last_name": "Mitarbeiter", "username": "radiology-employee",
        "password": "radiology-employee-password",
        "role_key": "EMPLOYEE",
        "department_id": departments["Radiologie"],
        "employee_id": employees["Radiologie"],
    })
    assert other_employee_account.status_code == 201
    headers = _login_headers(client, "surgery-planner", "surgery-planner-password")

    assert {
        employee["id"] for employee in client.get("/api/employees", headers=headers).json()
    } == {employees["Chirurgie"]}
    assert {
        shift["id"] for shift in client.get("/api/shift-types", headers=headers).json()
    } == {shifts["Chirurgie"]}
    visible_assignments = client.get(
        "/api/assignments?from=2031-02-05&to=2031-02-05", headers=headers
    )
    assert visible_assignments.status_code == 200
    assert {item["employee_id"] for item in visible_assignments.json()} == {
        employees["Chirurgie"]
    }

    cross_department_assignment = client.post("/api/assignments", headers=headers, json={
        "employee_id": employees["Radiologie"],
        "shift_type_id": shifts["Radiologie"],
        "starts_at": "2031-02-06T07:00:00+00:00",
        "ends_at": "2031-02-06T15:00:00+00:00",
    })
    assert cross_department_assignment.status_code == 403
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.put(
        f"/api/users/{other_employee_account.json()['id']}",
        headers=headers,
        json={
            "first_name": "Radiologie", "last_name": "Mitarbeiter",
            "username": "radiology-employee", "role_key": "EMPLOYEE",
            "department_id": departments["Radiologie"],
            "employee_id": employees["Radiologie"],
            "can_view": True,
        },
    ).status_code == 403


def test_users_can_switch_between_all_assigned_department_plans(client):
    admin = auth_header(client)
    departments = [
        client.post("/api/departments", headers=admin, json={"name": name}).json()
        for name in ("Neurologie", "Kardiologie", "Radiologie")
    ]
    planner = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "multi-planner",
            "password": "multi-plan-pass-8",
            "role_key": "OBERARZT",
            "department_ids": [departments[0]["id"], departments[1]["id"]],
            "can_view": True,
            "can_edit": True,
        },
    )
    assert planner.status_code == 201
    assert planner.json()["department_ids"] == [departments[0]["id"], departments[1]["id"]]

    client.post("/api/auth/login", json={"username": "multi-planner", "password": "multi-plan-pass-8"})
    for department in departments[:2]:
        assert client.post(
            "/api/shift-types",
            json={
                "name": f"{department['name']} Früh",
                "start_time": "07:00:00",
                "end_time": "15:00:00",
                "department_id": department["id"],
            },
        ).status_code == 201

    other_planner = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "radiology-planner",
            "password": "radiology-password-8",
            "role_key": "OBERARZT",
            "department_ids": [departments[2]["id"]],
            "can_view": True,
            "can_edit": True,
        },
    )
    assert other_planner.status_code == 201
    client.post("/api/auth/login", json={"username": "radiology-planner", "password": "radiology-password-8"})
    assert client.post(
        "/api/shift-types",
        json={
            "name": f"{departments[2]['name']} Früh",
            "start_time": "07:00:00",
            "end_time": "15:00:00",
            "department_id": departments[2]["id"],
        },
    ).status_code == 201

    client.post("/api/auth/login", json={"username": "multi-planner", "password": "multi-plan-pass-8"})
    assert {item["id"] for item in client.get("/api/departments").json()} == {
        departments[0]["id"], departments[1]["id"],
    }
    visible_shifts = client.get("/api/shift-types").json()
    assert {item["department_id"] for item in visible_shifts} == {
        departments[0]["id"], departments[1]["id"],
    }
    assert client.post(
        "/api/shift-types",
        json={
            "name": "Radiologie unzulässig",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "department_id": departments[2]["id"],
        },
    ).status_code == 403


def test_password_check_uses_pwned_password_range_prefix_only(client, monkeypatch):
    password = "ClinicPulse-Testing-2026!"
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    requested_urls = []

    class ResponseStub:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self, _limit):
            return f"{digest[5:]}:42\n".encode("ascii")

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        assert timeout == 4
        assert request.get_header("Add-padding") == "true"
        return ResponseStub()

    monkeypatch.setattr(main.urllib.request, "urlopen", fake_urlopen)
    checked = client.post("/api/password/check", json={"password": password})
    assert checked.status_code == 200
    assert checked.json() == {"compromised_count": 42}
    assert requested_urls == [f"https://api.pwnedpasswords.com/range/{digest[:5]}"]
    assert client.post("/api/password/check", json={"password": "short"}).status_code == 422


def test_hospital_management_manages_accounts_but_cannot_edit_schedules(client):
    admin = auth_header(client)
    manager = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "management",
            "password": "management-password-123",
            "role_key": "HOSPITAL_MANAGEMENT",
            "can_view": False,
            "can_edit": True,
            "can_approve": True,
        },
    )
    assert manager.status_code == 201
    assert manager.json()["can_view"] is True
    client.post("/api/auth/login", json={"username": "management", "password": "management-password-123"})
    headers = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    assert client.get("/api/roles", headers=headers).status_code == 200
    assert client.post("/api/departments", json={"name": "Emergency"}, headers=headers).status_code == 201
    assert client.post(
        "/api/shift-types",
        headers=headers,
        json={"name": "Restricted", "start_time": "07:00:00", "end_time": "15:00:00"},
    ).status_code == 403
    assert client.post(
        "/api/users",
        headers=headers,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "manager2",
            "password": "manager-password-1234",
            "role_key": "HOSPITAL_MANAGEMENT",
        },
    ).status_code == 403


def _login_headers(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}


def test_employee_self_service_absence_workflow(client):
    admin = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    employee_id = client.post(
        "/api/employees",
        headers=admin,
        json={"first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id},
    ).json()["id"]
    other_id = client.post(
        "/api/employees",
        headers=admin,
        json={"first_name": "Max", "last_name": "Muster", "role": "Chirurg", "department_id": department_id},
    ).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    unlinked = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "erika", "password": "secure-password-123", "role_key": "EMPLOYEE",
        "department_id": department_id,
    })
    assert unlinked.status_code == 422
    created = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "erika", "password": "secure-password-123", "role_key": "EMPLOYEE",
        "department_id": department_id, "employee_id": employee_id,
    })
    assert created.status_code == 201
    assert created.json()["employee_id"] == employee_id
    duplicate = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "erika2", "password": "secure-password-123", "role_key": "EMPLOYEE",
        "department_id": department_id, "employee_id": employee_id,
    })
    assert duplicate.status_code == 409

    employee = _login_headers(client, "erika", "secure-password-123")
    request = client.post("/api/absences", headers=employee, json={
        "kind": "vacation", "start_date": "2030-03-04", "end_date": "2030-03-08", "note": "Urlaub",
    })
    assert request.status_code == 201
    assert request.json()["status"] == "pending"
    absence_id = request.json()["id"]
    assert client.post("/api/absences", headers=employee, json={
        "employee_id": other_id, "kind": "sick", "start_date": "2030-04-01", "end_date": "2030-04-02",
    }).status_code == 403
    assert client.post("/api/absences", headers=employee, json={
        "kind": "sick", "start_date": "2030-03-06", "end_date": "2030-03-06",
    }).status_code == 409
    assert request.json()["requested_by"] == "erika"
    assert client.post(f"/api/absences/{absence_id}/decision", headers=employee, json={"decision": "approved"}).status_code == 403
    sick = client.post("/api/absences", headers=employee, json={
        "kind": "sick", "start_date": "2030-05-01", "end_date": "2030-05-02",
    })
    assert sick.status_code == 201
    assert sick.json()["status"] == "approved" and sick.json()["decided_by"] is None
    assert client.post(f"/api/absences/{sick.json()['id']}/decision", headers=employee, json={"decision": "approved"}).status_code in (403, 409)

    planner = _login_headers(client, "planner", "secure-password-123")
    assert [item["id"] for item in client.get("/api/absences?status=pending", headers=planner).json()] == [absence_id]
    decision = client.post(f"/api/absences/{absence_id}/decision", headers=planner, json={"decision": "approved"})
    assert decision.status_code == 200
    assert decision.json()["decided_by"] == "planner"

    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Früh", "start_time": "07:00:00", "end_time": "15:00:00", "position": "Chirurg",
    }).json()["id"]
    blocked = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-03-05T07:00:00+00:00", "ends_at": "2030-03-05T15:00:00+00:00",
    })
    assert blocked.status_code == 409
    candidates = client.get("/api/smart-selection", headers=planner, params={
        "shift_type_id": shift_id, "starts_at": "2030-03-05T07:00:00+00:00", "ends_at": "2030-03-05T15:00:00+00:00",
    }).json()["candidates"]
    assert [item["employee_id"] for item in candidates] == [other_id]
    assert client.delete(f"/api/absences/{absence_id}", headers=employee).status_code == 409
    assert client.get("/api/absences", headers=_login_headers(client, "erika", "secure-password-123")).json()[-1]["id"] == absence_id


def test_minimum_rest_period_blocks_assignments_and_suggestions(client):
    admin = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    planner = _login_headers(client, "planner", "secure-password-123")
    late = client.post("/api/shift-types", headers=planner, json={
        "name": "Spät", "start_time": "14:00:00", "end_time": "22:00:00", "position": "Chirurg",
    }).json()["id"]
    early = client.post("/api/shift-types", headers=planner, json={
        "name": "Früh", "start_time": "06:00:00", "end_time": "14:00:00", "position": "Chirurg",
    }).json()["id"]
    first = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": late,
        "starts_at": "2030-03-05T14:00:00+00:00", "ends_at": "2030-03-05T22:00:00+00:00",
    })
    assert first.status_code == 201
    too_soon = {
        "employee_id": employee_id, "shift_type_id": early,
        "starts_at": "2030-03-06T06:00:00+00:00", "ends_at": "2030-03-06T14:00:00+00:00",
    }
    rejected = client.post("/api/assignments", headers=planner, json=too_soon)
    assert rejected.status_code == 409
    assert "rest period" in rejected.json()["detail"]
    suggestions = client.get("/api/smart-selection", headers=planner, params={
        "shift_type_id": early, "starts_at": too_soon["starts_at"], "ends_at": too_soon["ends_at"],
    }).json()["candidates"]
    assert suggestions == []
    ok = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": early,
        "starts_at": "2030-03-06T09:00:00+00:00", "ends_at": "2030-03-06T17:00:00+00:00",
    })
    assert ok.status_code == 201


def test_working_time_limits_breaks_and_configurable_rules(client):
    admin = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    planner = _login_headers(client, "planner", "secure-password-123")

    assert client.get("/api/admin/work-rules", headers=admin).json() == {
        "rest_hours": 11, "max_daily_hours": 10, "max_weekly_hours": 48,
    }
    assert client.put("/api/admin/work-rules", headers=planner, json={
        "rest_hours": 11, "max_daily_hours": 10, "max_weekly_hours": 48,
    }).status_code == 403
    assert client.put("/api/admin/work-rules", headers=admin, json={
        "rest_hours": 8, "max_daily_hours": 10, "max_weekly_hours": 48,
    }).status_code == 422
    assert client.put("/api/admin/work-rules", headers=admin, json={
        "rest_hours": 10, "max_daily_hours": 10, "max_weekly_hours": 48,
    }).status_code == 422
    assert client.put("/api/admin/work-rules", headers=admin, json={
        "rest_hours": 11, "max_daily_hours": 10, "max_weekly_hours": 49,
    }).status_code == 422

    auto = client.post("/api/shift-types", headers=planner, json={
        "name": "Lang", "start_time": "07:00:00", "end_time": "18:30:00", "position": "Chirurg",
    })
    assert auto.status_code == 201
    assert auto.json()["break_minutes"] == 45
    short_break = client.post("/api/shift-types", headers=planner, json={
        "name": "Spät", "start_time": "14:00:00", "end_time": "22:00:00", "position": "Chirurg", "break_minutes": 10,
    })
    assert short_break.status_code == 422
    nine_and_half_hours = client.post("/api/shift-types", headers=planner, json={
        "name": "Lang genau", "start_time": "08:00:00", "end_time": "17:30:00", "position": "Chirurg",
    })
    assert nine_and_half_hours.status_code == 201
    assert nine_and_half_hours.json()["break_minutes"] == 30
    nine_and_a_bit_hours = client.post("/api/shift-types", headers=planner, json={
        "name": "Lang plus", "start_time": "08:00:00", "end_time": "17:31:00", "position": "Chirurg",
    })
    assert nine_and_a_bit_hours.status_code == 201
    assert nine_and_a_bit_hours.json()["break_minutes"] == 45
    extended_pause = client.post("/api/shift-types", headers=planner, json={
        "name": "Lang mit Pause", "start_time": "08:00:00", "end_time": "17:40:00",
        "position": "Chirurg", "break_minutes": 40,
    })
    assert extended_pause.status_code == 201
    assert extended_pause.json()["break_minutes"] == 40

    long_shift = auto.json()["id"]
    over_daily = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": long_shift,
        "starts_at": "2030-03-05T07:00:00+00:00", "ends_at": "2030-03-05T18:30:00+00:00",
    })
    assert over_daily.status_code == 409
    assert "Daily working time" in over_daily.json()["detail"]

    day = client.post("/api/shift-types", headers=planner, json={
        "name": "Tag", "start_time": "08:00:00", "end_time": "16:00:00", "position": "Chirurg",
    }).json()["id"]
    for offset in range(5):
        created = client.post("/api/assignments", headers=planner, json={
            "employee_id": employee_id, "shift_type_id": day,
            "starts_at": f"2030-03-{4 + offset:02d}T08:00:00+00:00", "ends_at": f"2030-03-{4 + offset:02d}T16:00:00+00:00",
        })
        assert created.status_code == 201
    assert client.put("/api/admin/work-rules", headers=admin, json={
        "rest_hours": 11, "max_daily_hours": 10, "max_weekly_hours": 40,
    }).status_code == 200
    weekend = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": day,
        "starts_at": "2030-03-09T08:00:00+00:00", "ends_at": "2030-03-09T16:00:00+00:00",
    })
    assert weekend.status_code == 201


def test_business_configuration_is_selected_during_setup_and_admin_editable(client):
    response = client.post("/api/setup", json={
        "username": "setup-admin",
        "password": "secure-password-123",
        "license_token": os.environ["TEST_LICENSE_TOKEN"],
        "federal_state": "Bayern",
        "operational_profile": "rescue_service",
    })
    assert response.status_code == 201
    admin = {"Authorization": f"Bearer {client.cookies.get('clinicpulse_session')}"}
    config = client.get("/api/admin/business-configuration", headers=admin)
    assert config.status_code == 200
    assert config.json() == {
        "federal_state": "Bayern",
        "operational_profile": "rescue_service",
        "operational_profile_managed": False,
        "federal_state_managed": False,
        "timezone": "Europe/Berlin",
        "sunday_work_authorized": False,
    }
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Sachsen",
        "operational_profile": "ils",
        "sunday_work_authorized": True,
    }).json()["operational_profile"] == "ils"
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Mars",
        "operational_profile": "hospital",
    }).status_code == 422


def test_24_week_average_allows_busy_week_but_enforces_reference_average(client):
    from datetime import date, datetime, time, timedelta, timezone

    from app.database import SessionLocal
    from app.models import Assignment, ShiftType

    admin = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    planner = _login_headers(client, "planner", "secure-password-123")
    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Tag", "start_time": "08:00:00", "end_time": "16:30:00", "position": "Chirurg",
    }).json()["id"]
    assert client.put("/api/admin/work-rules", headers=admin, json={
        "rest_hours": 11, "max_daily_hours": 10, "max_weekly_hours": 20,
    }).status_code == 200
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Nordrhein-Westfalen",
        "operational_profile": "hospital",
        "sunday_work_authorized": True,
    }).status_code == 200

    first_monday = date(2030, 1, 7)
    with SessionLocal() as db:
        shift = db.get(ShiftType, shift_id)
        assert shift is not None
        assignments = []
        for week in range(24):
            weekdays = (0, 4) if week >= 12 else (0, 2, 4)
            for weekday in weekdays:
                work_date = first_monday + timedelta(days=week * 7 + weekday)
                starts_at = datetime.combine(work_date, time(8), tzinfo=timezone.utc)
                assignments.append(Assignment(
                    employee_id=employee_id,
                    shift_type_id=shift_id,
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(hours=8, minutes=30),
                ))
        db.add_all(assignments)
        db.commit()
    # 60 shifts x 8 net hours = 480 hours, exactly 20 hours/week on average.
    candidate_date = first_monday + timedelta(days=23 * 7 + 6)
    extra = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": datetime.combine(candidate_date, time(8), tzinfo=timezone.utc).isoformat(),
        "ends_at": datetime.combine(candidate_date, time(16, 30), tzinfo=timezone.utc).isoformat(),
    })
    assert extra.status_code == 409
    assert "24-week reference period" in extra.json()["detail"]


def test_work_break_must_be_scheduled_before_six_continuous_hours(client):
    admin = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True,
    }).status_code == 201
    planner = _login_headers(client, "planner", "secure-password-123")
    invalid = client.post("/api/shift-types", headers=planner, json={
        "name": "Spät", "start_time": "08:00:00", "end_time": "16:00:00",
        "position": "Chirurg", "break_start_minutes": 361,
    })
    assert invalid.status_code == 422
    valid = client.post("/api/shift-types", headers=planner, json={
        "name": "Früh", "start_time": "08:00:00", "end_time": "16:00:00",
        "position": "Chirurg", "break_start_minutes": 360,
    })
    assert valid.status_code == 201
    overnight = client.post("/api/shift-types", headers=planner, json={
        "name": "Nacht", "start_time": "18:00:00", "end_time": "08:00:00",
        "position": "Chirurg", "break_minutes": 45, "break_start_minutes": 360,
    })
    assert overnight.status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Nacht", "last_name": "wache", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    response = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id,
        "shift_type_id": overnight.json()["id"],
        "starts_at": "2030-03-05T18:00:00+00:00",
        "ends_at": "2030-03-06T08:00:00+00:00",
    })
    assert response.status_code == 409
    assert "longer than six hours" in response.json()["detail"]


def test_sundays_and_state_public_holidays_require_explicit_authorization(client):
    admin = auth_header(client)
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Nordrhein-Westfalen",
        "operational_profile": "hospital",
        "sunday_work_authorized": False,
    }).status_code == 200
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True,
    }).status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    planner = _login_headers(client, "planner", "secure-password-123")
    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Tag", "start_time": "08:00:00", "end_time": "16:30:00", "position": "Chirurg",
    }).json()["id"]

    sunday = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-03-10T07:00:00+00:00", "ends_at": "2030-03-10T15:30:00+00:00",
    })
    assert sunday.status_code == 409
    assert "ArbZG §§9–10" in sunday.json()["detail"]

    holiday = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-06-20T06:00:00+00:00", "ends_at": "2030-06-20T14:30:00+00:00",
    })
    assert holiday.status_code == 409
    assert "ArbZG §§9–10" in holiday.json()["detail"]
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Sachsen",
        "operational_profile": "hospital",
        "sunday_work_authorized": False,
    }).status_code == 200
    not_a_saxony_holiday = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-06-20T06:00:00+00:00", "ends_at": "2030-06-20T14:30:00+00:00",
    })
    assert not_a_saxony_holiday.status_code == 201
    day_after_holiday = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-06-21T06:00:00+00:00", "ends_at": "2030-06-21T14:30:00+00:00",
    })
    assert day_after_holiday.status_code == 201


def test_15_sunday_rest_days_and_replacement_rest_days_are_enforced(client):
    from datetime import date, datetime, time, timedelta, timezone

    from app.database import SessionLocal
    from app.models import Assignment, ShiftType

    admin = auth_header(client)
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Berlin",
        "operational_profile": "hospital",
        "sunday_work_authorized": True,
    }).status_code == 200
    department_id = client.post("/api/departments", json={"name": "Chirurgie"}, headers=admin).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "planner", "password": "secure-password-123", "role_key": "OBERARZT",
        "department_id": department_id, "can_view": True, "can_edit": True,
    }).status_code == 201
    employee_id = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Chirurg", "department_id": department_id,
    }).json()["id"]
    planner = _login_headers(client, "planner", "secure-password-123")
    shift_id = client.post("/api/shift-types", headers=planner, json={
        "name": "Tag", "start_time": "08:00:00", "end_time": "16:30:00", "position": "Chirurg",
    }).json()["id"]
    with SessionLocal() as db:
        shift = db.get(ShiftType, shift_id)
        assert shift is not None
        sunday_assignments = []
        first_sunday = date(2030, 1, 6)
        for week in range(37):
            starts_at = datetime.combine(
                first_sunday + timedelta(days=week * 7), time(7), tzinfo=timezone.utc
            )
            sunday_assignments.append(Assignment(
                employee_id=employee_id,
                shift_type_id=shift_id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=8, minutes=30),
            ))
        db.add_all(sunday_assignments)
        db.commit()
    thirty_eighth_sunday = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-09-22T07:00:00+00:00", "ends_at": "2030-09-22T15:30:00+00:00",
    })
    assert thirty_eighth_sunday.status_code == 409
    assert "15 Sundays" in thirty_eighth_sunday.json()["detail"]

    with SessionLocal() as db:
        db.query(Assignment).filter(Assignment.employee_id == employee_id).delete()
        candidate_sunday = date(2030, 3, 10)
        for offset in range(-13, 14):
            if offset == 0:
                continue
            starts_at = datetime.combine(
                candidate_sunday + timedelta(days=offset), time(7), tzinfo=timezone.utc
            )
            db.add(Assignment(
                employee_id=employee_id,
                shift_type_id=shift_id,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=8, minutes=30),
            ))
        db.commit()
    no_rest_day = client.post("/api/assignments", headers=planner, json={
        "employee_id": employee_id, "shift_type_id": shift_id,
        "starts_at": "2030-03-10T07:00:00+00:00", "ends_at": "2030-03-10T15:30:00+00:00",
    })
    assert no_rest_day.status_code == 409
    assert "replacement rest day" in no_rest_day.json()["detail"]


def test_operational_profile_is_taken_from_license_and_locked(client, license_key):
    token = jwt.encode(
        {
            "iss": "clinicpulse-licensing",
            "aud": "clinicpulse",
            "sub": "managed-customer",
            "jti": "managed-license-1",
            "institution_name": "Rettungswache Nord",
            "operational_profile": "rescue_service",
            "federal_state": "Sachsen",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
            "license_status": "PAID",
        },
        license_key,
        algorithm="RS256",
    )
    response = client.post("/api/setup", json={
        "username": "managed-admin",
        "password": "secure-password-123",
        "license_token": token,
    })
    assert response.status_code == 201
    config = client.get("/api/admin/business-configuration").json()
    assert config["operational_profile"] == "rescue_service"
    assert config["operational_profile_managed"] is True
    assert config["federal_state"] == "Sachsen"
    assert config["federal_state_managed"] is True
    update = client.put("/api/admin/business-configuration", json={
        "federal_state": "Bayern",
        "operational_profile": "hospital",
    })
    assert update.status_code == 200
    assert update.json()["federal_state"] == "Sachsen"
    assert update.json()["operational_profile"] == "rescue_service"
    assert client.get("/api/license/status").json()["operational_profile"] == "rescue_service"


def test_setup_without_license_profile_requires_manual_choice(client):
    response = client.post("/api/setup", json={
        "username": "manual-admin",
        "password": "secure-password-123",
        "license_token": os.environ["TEST_LICENSE_TOKEN"],
        "federal_state": "Bayern",
    })
    assert response.status_code == 422


def test_admin_can_lock_users_view_login_log_but_not_schedules(client):
    admin = auth_header(client)
    created = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "lock-me", "password": "C0mp!ex8", "role_key": "KIOSK", "can_view": True,
    })
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert client.post("/api/auth/login", json={"username": "lock-me", "password": "C0mp!ex8"}).status_code == 200
    locked = client.put(f"/api/users/{user_id}/lock", headers=admin, json={"locked": True})
    assert locked.status_code == 200 and locked.json()["is_locked"] is True
    assert client.post("/api/auth/login", json={"first_name": "Test", "last_name": "Nutzer", "username": "lock-me", "password": "C0mp!ex8"}).status_code == 401
    assert client.put(f"/api/users/{user_id}/lock", headers=admin, json={"locked": False}).status_code == 200
    assert client.post("/api/auth/login", json={"first_name": "Test", "last_name": "Nutzer", "username": "lock-me", "password": "C0mp!ex8"}).status_code == 200
    log = client.get("/api/admin/audit?category=logins", headers=admin).json()["items"]
    assert {"login", "login_failed", "locked", "unlocked"} <= {item["action"] for item in log}
    plan = client.get("/api/assignments?from=2025-01-01&to=2025-01-07", headers=admin)
    assert plan.status_code == 403


def test_disabled_mail_creates_accounts_with_enforced_password_change(client, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_invitation", lambda *args: sent.append(args))
    monkeypatch.setattr(main, "send_test_email", lambda *args: sent.append(args))
    admin = auth_header(client)
    assert client.get("/api/account-creation/mail-mode", headers=admin).json() == {"enabled": True}
    assert client.put("/api/admin/mail-mode", headers=admin, json={"enabled": False}).status_code == 200
    assert client.get("/api/account-creation/mail-mode", headers=admin).json() == {"enabled": False}
    assert client.post("/api/admin/mail-settings/test", headers=admin, json={"recipient": "a@example.test"}).status_code == 409
    department_id = client.post("/api/departments", headers=admin, json={"name": "Station"}).json()["id"]
    base = {"first_name": "Erika", "last_name": "Beispiel", "username": "offline-user", "role_key": "HOSPITAL_MANAGEMENT"}
    assert client.post("/api/users", headers=admin, json={**base, "email": "a@example.test"}).status_code == 422
    created = client.post("/api/users", headers=admin, json={**base, "email": "a@example.test", "password": "start-password"})
    assert created.status_code == 201
    assert created.json()["invitation_status"] == "active"
    assert created.json()["is_locked"] is False
    assert client.post(f"/api/users/{created.json()['id']}/invitation", headers=admin).status_code == 409

    onboard = {
        "first_name": "Ada", "last_name": "Beispiel", "role": "Pflege", "department_id": department_id,
        "create_account": True, "username": "offline-employee",
    }
    assert client.post("/api/employees/onboard", headers=admin, json=onboard).status_code == 422
    assert client.get("/api/employees", headers=admin).json() == []
    response = client.post("/api/employees/onboard", headers=admin, json={**onboard, "password": "employee-start"})
    assert response.status_code == 201
    assert response.json()["invitation_status"] is None
    assert sent == []

    for username, initial in [("offline-user", "start-password"), ("offline-employee", "employee-start")]:
        login = client.post("/api/auth/login", json={"username": username, "password": initial})
        assert login.status_code == 200 and login.json()["must_change_password"] is True
        token = client.cookies.get("clinicpulse_session")
        restricted = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/auth/session", headers=restricted).json()["must_change_password"] is True
        assert client.get("/api/departments", headers=restricted).status_code == 403
        assert client.get("/api/users", headers=restricted).status_code == 403
        payload = {"username": username, "current_password": initial}
        assert client.put("/api/settings/account", headers=restricted, json=payload).status_code == 422
        assert client.put("/api/settings/account", headers=restricted, json={**payload, "new_password": initial}).status_code == 422
        assert client.put("/api/settings/account", headers=restricted, json={**payload, "username": "changed", "new_password": "different-password"}).status_code == 422
        changed = client.put("/api/settings/account", json={**payload, "new_password": "different-password"})
        assert changed.status_code == 200 and changed.json()["must_change_password"] is False
        assert client.get("/api/auth/session", headers=restricted).status_code == 401
        assert client.post("/api/auth/login", json={"username": username, "password": initial}).status_code == 401
        assert client.post("/api/auth/login", json={"username": username, "password": "different-password"}).status_code == 200
        assert client.put("/api/admin/mail-mode", json={"enabled": True}).status_code == 403
        if username == "offline-employee":
            assert client.get("/api/account-creation/mail-mode").status_code == 403
    assert client.put("/api/admin/mail-mode", headers=admin, json={"enabled": True}).status_code == 200
    assert client.get("/api/account-creation/mail-mode", headers=admin).json() == {"enabled": True}


def test_existing_invitation_can_be_converted_to_temporary_password(client, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_invitation", lambda recipient, username, token, config: sent.append(token))
    admin = auth_header(client)
    body = {"first_name": "Test", "last_name": "Person", "username": "invited", "role_key": "HOSPITAL_MANAGEMENT", "email": "person@example.test"}
    created = client.post("/api/users", headers=admin, json=body)
    assert created.status_code == 201 and created.json()["invitation_status"] == "pending"
    client.put("/api/admin/mail-mode", headers=admin, json={"enabled": False})
    changed = client.put(f"/api/users/{created.json()['id']}", headers=admin, json={**body, "new_password": "initial-password"})
    assert changed.status_code == 200
    assert changed.json()["invitation_status"] == "active" and not changed.json()["is_locked"]
    assert client.post("/api/auth/accept-invitation", json={"token": sent[0], "password": "new-password"}).status_code == 400
    assert client.post("/api/auth/login", json={"username": "invited", "password": "initial-password"}).json()["must_change_password"] is True


def test_legacy_mail_and_password_change_columns_migrate_with_safe_defaults(client):
    admin = auth_header(client)
    created = client.post("/api/users", headers=admin, json={
        "first_name": "Alt", "last_name": "Nutzer", "username": "legacy-user",
        "password": "legacy-password", "role_key": "HOSPITAL_MANAGEMENT",
    })
    assert created.status_code == 201
    with main.engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE user_accounts DROP COLUMN must_change_password")
        connection.exec_driver_sql("ALTER TABLE application_settings DROP COLUMN mail_enabled")
    main.migrate_existing_database()
    main.migrate_existing_database()
    assert "must_change_password" in {column["name"] for column in inspect(main.engine).get_columns("user_accounts")}
    assert "mail_enabled" in {column["name"] for column in inspect(main.engine).get_columns("application_settings")}
    assert client.get("/api/account-creation/mail-mode", headers=admin).json() == {"enabled": True}
    login = client.post("/api/auth/login", json={"username": "legacy-user", "password": "legacy-password"})
    assert login.status_code == 200 and login.json()["must_change_password"] is False


def test_mail_mode_preserves_smtp_settings_and_reenables_invitations(client, monkeypatch):
    sent = []
    monkeypatch.setattr(main, "send_invitation", lambda *args: sent.append(args))
    admin = auth_header(client)
    config = {
        "public_url": "https://clinic.example.test", "smtp_host": "mail.example.test", "smtp_port": 587,
        "smtp_username": "clinic", "smtp_password": "secret", "from_address": "clinic@example.test",
        "use_ssl": False, "use_starttls": True,
    }
    assert client.put("/api/admin/mail-settings", headers=admin, json=config).status_code == 200
    assert client.put("/api/admin/mail-mode", headers=admin, json={"enabled": False}).status_code == 200
    assert client.put("/api/admin/mail-mode", headers=admin, json={"enabled": True}).status_code == 200
    saved = client.get("/api/admin/mail-settings", headers=admin).json()
    assert saved["smtp_host"] == config["smtp_host"] and saved["smtp_password_configured"] is True
    created = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Person", "username": "mail-user",
        "email": "person@example.test", "role_key": "HOSPITAL_MANAGEMENT",
    })
    assert created.status_code == 201 and created.json()["invitation_status"] == "pending"
    assert sent[0][0] == "person@example.test" and sent[0][3].smtp_password == "secret"


def test_employee_invitation_sets_password_once_and_resend_revokes_old_link(client, monkeypatch):
    sent = []

    def fake_send(recipient, username, token, configuration=None):
        sent.append((recipient, username, token, configuration))

    monkeypatch.setattr(main, "send_invitation", fake_send)
    admin = auth_header(client)
    department_id = client.post(
        "/api/departments", headers=admin, json={"name": "Einladung"}
    ).json()["id"]
    created = client.post(
        "/api/employees/onboard",
        headers=admin,
        json={
            "first_name": "Erika", "last_name": "Beispiel",
            "role": "Assistenzarzt",
            "department_id": department_id,
            "create_account": True,
            "username": "erika-beispiel",
            "email": "erika@example.test",
        },
    )
    assert created.status_code == 201
    assert created.json()["invitation_status"] == "pending"
    assert sent[0][:2] == ("erika@example.test", "erika-beispiel")
    assert client.post(
        "/api/auth/login",
        json={"username": "erika-beispiel", "password": "unbekannt"},
    ).status_code == 401

    user = client.get("/api/users", headers=admin).json()[0]
    assert user["invitation_status"] == "pending"
    assert user["is_locked"] is True
    user_id = user["id"]
    old_token = sent[0][2]
    revoked = client.delete(f"/api/users/{user_id}/invitation", headers=admin)
    assert revoked.status_code == 204
    assert client.post(
        "/api/auth/accept-invitation",
        json={"token": old_token, "password": "neues-passwort-123"},
    ).status_code == 400
    resent = client.post(f"/api/users/{user_id}/invitation", headers=admin)
    assert resent.status_code == 200
    assert sent[1][2] != old_token
    assert client.post(
        "/api/auth/accept-invitation",
        json={"token": old_token, "password": "neues-passwort-123"},
    ).status_code == 400

    accepted = client.post(
        "/api/auth/accept-invitation",
        json={"token": sent[1][2], "password": "neues-passwort-123"},
    )
    assert accepted.status_code == 204
    assert client.post(
        "/api/auth/accept-invitation",
        json={"token": sent[1][2], "password": "anderes-passwort-123"},
    ).status_code == 400
    login = client.post(
        "/api/auth/login",
        json={"username": "erika-beispiel", "password": "neues-passwort-123"},
    )
    assert login.status_code == 200


def test_admin_can_save_mail_settings_and_send_a_test_message(client, monkeypatch):
    sent = []

    def fake_test_email(recipient, configuration):
        sent.append((recipient, configuration))

    monkeypatch.setattr(main, "send_test_email", fake_test_email)
    admin = auth_header(client)
    payload = {
        "public_url": "https://clinic.example.test",
        "smtp_host": "mail.example.test",
        "smtp_port": 587,
        "smtp_username": "clinicpulse",
        "smtp_password": "private-mail-password",
        "from_address": "clinicpulse@example.test",
        "use_ssl": False,
        "use_starttls": True,
    }
    saved = client.put("/api/admin/mail-settings", headers=admin, json=payload)
    assert saved.status_code == 200
    assert saved.json()["smtp_password_configured"] is True
    assert "private-mail-password" not in saved.text

    read = client.get("/api/admin/mail-settings", headers=admin)
    assert read.status_code == 200
    assert read.json()["smtp_host"] == "mail.example.test"
    assert "smtp_password" not in read.json()
    tested = client.post(
        "/api/admin/mail-settings/test",
        headers=admin,
        json={"recipient": "admin@example.test"},
    )
    assert tested.status_code == 200
    assert sent[0][0] == "admin@example.test"
    assert sent[0][1].smtp_password == "private-mail-password"

    preserved = client.put(
        "/api/admin/mail-settings",
        headers=admin,
        json={**payload, "smtp_password": None},
    )
    assert preserved.status_code == 200
    assert preserved.json()["smtp_password_configured"] is True
    insecure = client.put(
        "/api/admin/mail-settings",
        headers=admin,
        json={**payload, "smtp_password": None, "use_starttls": False},
    )
    assert insecure.status_code == 422

    manager = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "mail-manager",
            "password": "mail-manager-password-123",
            "role_key": "HOSPITAL_MANAGEMENT",
        },
    )
    assert manager.status_code == 201
    assert client.post(
        "/api/auth/login",
        json={"username": "mail-manager", "password": "mail-manager-password-123"},
    ).status_code == 200
    forbidden = client.get("/api/admin/mail-settings")
    assert forbidden.status_code == 403
    assert client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "test-password-with-twelve"},
    ).status_code == 200

    cleared = client.put(
        "/api/admin/mail-settings",
        headers=admin,
        json={**payload, "smtp_password": None, "clear_smtp_password": True},
    )
    assert cleared.status_code == 200
    assert cleared.json()["smtp_password_configured"] is False


def test_personnel_role_can_manage_staff_but_not_planning_or_privileged_accounts(client):
    admin = auth_header(client)
    department_id = client.post(
        "/api/departments", headers=admin, json={"name": "Personal"}
    ).json()["id"]
    personnel = client.post(
        "/api/users",
        headers=admin,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "personal",
            "password": "personal-passwort-123",
            "role_key": "PERSONNEL",
        },
    )
    assert personnel.status_code == 201
    assert personnel.json()["can_view"] is False
    assert client.post(
        "/api/auth/login",
        json={"username": "personal", "password": "personal-passwort-123"},
    ).status_code == 200

    staff = client.post(
        "/api/employees/onboard",
        json={
            "first_name": "Mara", "last_name": "Beispiel",
            "role": "Pflegefachkraft",
            "department_id": department_id,
        },
    )
    assert staff.status_code == 201
    assert client.get("/api/employees").status_code == 200
    forbidden = client.post(
        "/api/users",
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "oberarzt",
            "password": "oberarzt-passwort-123",
            "role_key": "OBERARZT",
            "department_id": department_id,
        },
    )
    assert forbidden.status_code == 403
    assert client.get("/api/assignments?from=2026-11-01&to=2026-11-07").status_code == 403


def test_plan_archive_snapshot_is_immutable_and_exports_pdf(client):
    admin_headers = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Archiv"}, headers=admin_headers).json()["id"]
    employee_id = client.post(
        "/api/employees",
        json={"first_name": "Äsop", "last_name": "Muster", "role": "Nurse", "department_id": department_id},
        headers=admin_headers,
    ).json()["id"]
    client.post(
        "/api/users",
        headers=admin_headers,
        json={
            "first_name": "Test", "last_name": "Nutzer", "username": "planner",
            "password": "planner-password-1234",
            "role_key": "OBERARZT",
            "department_id": department_id,
            "can_edit": True,
            "can_approve": True,
        },
    )
    client.post("/api/auth/login", json={"username": "planner", "password": "planner-password-1234"})
    headers: dict[str, str] = {}
    shift_id = client.post(
        "/api/shift-types",
        json={"name": "Früh", "start_time": "07:00:00", "end_time": "15:00:00", "color": "#2563eb",
              "position": "Nurse", "required_staff": 1, "department_id": department_id},
        headers=headers,
    ).json()["id"]
    assignment_id = client.post(
        "/api/assignments",
        json={"employee_id": employee_id, "shift_type_id": shift_id,
              "starts_at": "2026-10-14T07:00:00+02:00", "ends_at": "2026-10-14T15:00:00+02:00"},
        headers=headers,
    ).json()["id"]

    created = client.post(
        "/api/archives",
        json={"start_date": "2026-10-01", "end_date": "2026-10-31", "department_id": department_id},
        headers=headers,
    )
    assert created.status_code == 201
    archive_id = created.json()["id"]
    assert created.json()["entry_count"] == 1

    assert client.delete(f"/api/assignments/{assignment_id}", headers=headers).status_code in (200, 204, 404, 405)
    detail = client.get(f"/api/archives/{archive_id}", headers=headers).json()
    assert detail["integrity_ok"] is True
    assert detail["entries"][0]["employee_name"] == "Äsop Muster"
    assert detail["entries"][0]["shift_name"] == "Früh"

    pdf = client.get(f"/api/archives/{archive_id}/pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-1.4") and pdf.content.rstrip().endswith(b"%%EOF")

    assert client.delete(f"/api/archives/{archive_id}", headers=headers).status_code == 405
    client.post("/api/auth/login", json={"username": "test-admin", "password": "test-password-with-twelve"})
    assert client.get("/api/archives").status_code == 403


def test_automatic_archive_is_optional_and_archives_completed_periods(client):
    from app.database import SessionLocal
    from app.plan_archive import run_due_archive

    admin_headers = auth_header(client)
    department_id = client.post("/api/departments", json={"name": "Auto"}, headers=admin_headers).json()["id"]
    employee_id = client.post(
        "/api/employees", json={"first_name": "Max", "last_name": "Muster", "role": "Nurse", "department_id": department_id},
        headers=admin_headers,
    ).json()["id"]

    settings = client.get("/api/admin/archive-settings").json()
    assert settings["auto_enabled"] is False
    with SessionLocal() as db:
        assert run_due_archive(db, datetime(2026, 11, 3, 12, tzinfo=timezone.utc)) == []

    saved = client.put("/api/admin/archive-settings", json={"auto_enabled": True, "period": "monthly"})
    assert saved.status_code == 200
    assert saved.json()["auto_enabled"] is True

    from app import models
    with SessionLocal() as db:
        db.add(models.ShiftType(
            name="Nacht", start_time=datetime(2026, 1, 1, 22).time(), end_time=datetime(2026, 1, 1, 6).time(),
            position="Nurse", department_id=department_id,
        ))
        db.commit()
        shift = db.query(models.ShiftType).one()
        db.add(models.Assignment(
            employee_id=employee_id, shift_type_id=shift.id,
            starts_at=datetime(2026, 12, 5, 7, tzinfo=timezone.utc), ends_at=datetime(2026, 12, 5, 15, tzinfo=timezone.utc),
        ))
        settings_row = db.get(models.ArchiveSettings, 1)
        settings_row.last_period_end = datetime(2026, 11, 30).date()
        db.commit()

        assert run_due_archive(db, datetime(2026, 12, 20, 12, tzinfo=timezone.utc)) == []
        created = run_due_archive(db, datetime(2027, 1, 2, 12, tzinfo=timezone.utc))
        assert len(created) == 1
        assert created[0].entry_count == 1 and created[0].created_by == "System (automatisch)"
        assert (created[0].start_date.isoformat(), created[0].end_date.isoformat()) == ("2026-12-01", "2026-12-31")
        assert run_due_archive(db, datetime(2027, 1, 2, 12, tzinfo=timezone.utc)) == []

    off = client.put("/api/admin/archive-settings", json={"auto_enabled": False, "period": "weekly"})
    assert off.json()["auto_enabled"] is False


def test_logout_clears_session_cookie_and_idle_timeout_is_configurable(client):
    auth_header(client)
    assert client.get("/api/auth/session").json()["idle_timeout_minutes"] == 5
    assert client.put("/api/admin/security-settings", json={"idle_timeout_minutes": 0}).status_code == 422
    assert client.put("/api/admin/security-settings", json={"idle_timeout_minutes": 10}).json() == {"idle_timeout_minutes": 10}
    assert client.get("/api/auth/session").json()["idle_timeout_minutes"] == 10

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert "clinicpulse_session=" in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert client.get("/api/auth/session").status_code == 401


def test_role_catalog_follows_the_facility_type(client):
    admin = auth_header(client)
    hospital = client.get("/api/role-catalog", headers=admin).json()
    assert {role["key"] for role in hospital["access_roles"]} >= {"OBERARZT", "CHEFARZT"}
    assert "Arzt" in hospital["functions"] and "Rettungssanitäter" not in hospital["functions"]

    department_id = client.post("/api/departments", headers=admin, json={"name": "Wache"}).json()["id"]
    assert client.put("/api/admin/business-configuration", headers=admin, json={
        "federal_state": "Bayern",
        "operational_profile": "rescue_service",
    }).status_code == 200
    rescue = client.get("/api/role-catalog", headers=admin).json()
    keys = {role["key"] for role in rescue["access_roles"]}
    assert "OBERARZT" not in keys and "CHEFARZT" not in keys
    assert "Rettungssanitäter" in rescue["functions"] and "Arzt" not in rescue["functions"]
    assert {"key": "HOSPITAL_MANAGEMENT", "label": "Wachleitung"} in rescue["access_roles"]
    assert {role["key"] for role in client.get("/api/roles", headers=admin).json()} == {
        "HOSPITAL_MANAGEMENT", "PERSONNEL", "EMPLOYEE",
    }
    rejected = client.post("/api/users", headers=admin, json={
        "first_name": "Test", "last_name": "Nutzer", "username": "oberarzt1",
        "password": "oberarzt-passwort-123",
        "role_key": "OBERARZT",
        "department_id": department_id,
        "department_ids": [department_id],
    })
    assert rejected.status_code == 422


def test_user_requires_names_and_profile_details_flow_to_employee_listing(client):
    admin = auth_header(client)
    department_id = client.post("/api/departments", headers=admin, json={"name": "Station"}).json()["id"]
    employee = client.post("/api/employees", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "role": "Arzt", "department_id": department_id,
    })
    assert employee.status_code == 201 and employee.json()["name"] == "Erika Muster"
    missing = client.post("/api/users", headers=admin, json={
        "username": "erika", "password": "erika-passwort-123", "role_key": "EMPLOYEE",
        "department_id": department_id, "employee_id": employee.json()["id"],
    })
    assert missing.status_code == 422
    created = client.post("/api/users", headers=admin, json={
        "first_name": "Erika", "last_name": "Muster", "username": "erika", "password": "erika-passwort-123",
        "role_key": "EMPLOYEE", "department_id": department_id, "employee_id": employee.json()["id"],
        "birth_date": "1990-05-01", "address": "Musterweg 1", "phone": "0123",
    })
    assert created.status_code == 201
    assert created.json()["birth_date"] == "1990-05-01" and created.json()["address"] == "Musterweg 1"
    assert client.post("/api/auth/login", json={"username": "erika", "password": "erika-passwort-123"}).status_code == 200
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    saved = client.put("/api/profile/me", json={
        "profile_image_data": png, "profile_photo_visibility": "department",
        "first_name": "Erika", "last_name": "Mustermann", "phone": "0999",
    })
    assert saved.status_code == 200 and saved.json()["last_name"] == "Mustermann" and saved.json()["phone"] == "0999"
    listed = client.get("/api/employees").json()
    assert listed[0]["name"] == "Erika Mustermann" and listed[0]["profile_image_data"] == png
