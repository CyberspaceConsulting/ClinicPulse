"""Datenschutz-Prüfungen (Pflicht-Check "Datenschutz" in GitHub Actions).

Die Tests sichern grundlegende Datenschutzzusagen ab: personenbezogene Daten werden
verschlüsselt gespeichert, tauchen nicht in Logs, Protokollen oder API-Antworten auf, sind
nur für berechtigte Rollen sichtbar und werden nicht in Caches oder im Browser abgelegt.
Schlägt ein Test fehl, wurde eine dieser Zusagen verletzt oder ein neues Feld nicht bewusst
eingeordnet. Die Einordnung steht in den Listen unten und muss begründet werden.
"""

import json
import logging
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import String, Text

from app.database import Base, engine
from app.encrypted import EncryptedText
from test_api import _login_headers, auth_header

pytestmark = pytest.mark.privacy

REPO_ROOT = Path(__file__).resolve().parents[2]

# Spalten, deren Name auf personenbezogene oder geheime Inhalte hindeutet. Textspalten mit
# einem solchen Namen müssen mit EncryptedText gespeichert werden, außer sie stehen in einer
# der beiden Listen darunter.
PERSONAL_COLUMN_PATTERN = re.compile(
    r"name|email|phone|address|birth|note|image|token|secret|key|password|comment|text|created_by|actor"
)

# Bewusst unverschlüsselt: keine personenbezogenen oder geheimen Klartextdaten.
ACCEPTED_PLAINTEXT = {
    ("admin_account", "username_lookup"): "HMAC-Index zur Anmeldung, kein Klartext",
    ("admin_account", "password_salt"): "Salt des Passwort-Hashs",
    ("admin_account", "password_hash"): "Passwort-Hash, kein Passwort",
    ("user_accounts", "username_lookup"): "HMAC-Index zur Anmeldung, kein Klartext",
    ("user_accounts", "password_salt"): "Salt des Passwort-Hashs",
    ("user_accounts", "password_hash"): "Passwort-Hash, kein Passwort",
    ("user_accounts", "role_key"): "Zugriffsrolle als Schlüsselwort, keine Personendaten",
    ("account_invitations", "token_digest"): "SHA-256 des Einladungstokens, nicht das Token",
    ("application_settings", "mail_smtp_username"): "Betriebskonfiguration des Mailservers",
    ("application_settings", "mail_from_address"): "Betriebskonfiguration (Absenderadresse der Einrichtung)",
    ("backup_recipients", "name"): "Bezeichnung eines Backup-Schlüssels, keine Beschäftigtendaten",
    ("backup_recipients", "public_key"): "öffentlicher Schlüssel",
    ("backup_runs", "target_name"): "Name des Backup-Ziels",
    ("backup_runs", "filename"): "Dateiname des Backups",
    ("backup_targets", "name"): "Name des Backup-Ziels",
    ("departments", "name"): "Organisationsdaten, keine Personendaten",
    ("department_qualifications", "name"): "Organisationsdaten, keine Personendaten",
    ("shift_types", "name"): "Organisationsdaten, keine Personendaten",
    ("vehicles", "name"): "Fahrzeugkennung, keine Personendaten",
    ("plan_archives", "department_name"): "Organisationsdaten, keine Personendaten",
    ("plan_archives", "content_sha256"): "Prüfsumme, kein Inhalt",
    ("login_attempts", "key"): "Hash aus Benutzername und Adresse für die Anmeldesperre",
}

# Bekannte Lücken: Klartext, der verschlüsselt werden sollte. Wird eine Lücke geschlossen,
# muss der Eintrag entfernt werden (siehe test_known_privacy_gaps_are_still_open).
KNOWN_PLAINTEXT_GAPS = {
    ("plan_archives", "created_by"): "Benutzername der erstellenden Person",
    ("plan_archives", "note"): "Freitext-Notiz zum Archiv",
}

SENTINELS = {
    "first_name": "Sentinelvorname",
    "last_name": "Sentinelnachname",
    "invite_email": "sentinel.einladung@example.org",
    "username": "sentinel.benutzer",
    "password": "Sentinel-Passwort-9137!",
    "phone": "+49 151 99999999",
    "address": "Sentinelstraße 42, 12345 Sentinelstadt",
    "absence_note": "Sentinel-Notiz Arztbesuch",
}

FORBIDDEN_RESPONSE_KEYS = {
    "password", "password_hash", "password_salt", "signing_key", "token_digest",
    "mail_smtp_password", "smtp_password", "license_token", "access_token",
}


def _text_columns():
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, (String, Text)) or isinstance(column.type, EncryptedText):
                yield table.name, column


def test_personal_text_columns_are_encrypted_or_explicitly_classified():
    unclassified = [
        f"{table}.{column.name}"
        for table, column in _text_columns()
        if PERSONAL_COLUMN_PATTERN.search(column.name)
        and not isinstance(column.type, EncryptedText)
        and (table, column.name) not in ACCEPTED_PLAINTEXT
        and (table, column.name) not in KNOWN_PLAINTEXT_GAPS
    ]
    assert not unclassified, (
        "Neue Textspalten mit möglichem Personenbezug müssen mit EncryptedText gespeichert oder in "
        f"tests/backend/test_privacy.py begründet eingeordnet werden: {unclassified}"
    )


def test_privacy_classification_lists_have_no_stale_entries():
    columns = {(table, column.name): column for table, column in _text_columns()}
    stale = [key for key in (*ACCEPTED_PLAINTEXT, *KNOWN_PLAINTEXT_GAPS) if key not in columns]
    assert not stale, f"Einträge verweisen auf nicht mehr vorhandene Spalten: {stale}"
    assert not set(ACCEPTED_PLAINTEXT) & set(KNOWN_PLAINTEXT_GAPS)


def test_known_privacy_gaps_are_still_open():
    columns = {(table, column.name): column for table, column in _text_columns()}
    fixed = [key for key in KNOWN_PLAINTEXT_GAPS if isinstance(columns[key].type, EncryptedText)]
    assert not fixed, f"Lücke geschlossen, bitte aus KNOWN_PLAINTEXT_GAPS entfernen: {fixed}"


def test_core_personal_data_columns_use_encryption():
    required = {
        "employees": {"name", "first_name", "last_name"},
        "user_accounts": {
            "username", "email", "first_name", "last_name", "birth_date", "address", "phone", "profile_image_data",
        },
        "admin_account": {"username", "signing_key", "license_token"},
        "absences": {"note"},
        "audit_events": {"actor_username"},
        "application_settings": {"mail_smtp_password"},
    }
    for table_name, names in required.items():
        table = Base.metadata.tables[table_name]
        missing = [name for name in names if not isinstance(table.columns[name].type, EncryptedText)]
        assert not missing, f"{table_name}: {missing} müssen verschlüsselt gespeichert werden"


def _dump_raw_database() -> str:
    parts: list[str] = []
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            for row in connection.exec_driver_sql(f"SELECT * FROM {table.name}"):
                parts.extend(str(value) for value in row if value is not None)
    return "\n".join(parts)


def _create_sentinel_data(client):
    admin = auth_header(client)
    department = client.post("/api/departments", headers=admin, json={"name": "Datenschutz"}).json()["id"]
    employee = client.post("/api/employees", headers=admin, json={
        "first_name": SENTINELS["first_name"], "last_name": SENTINELS["last_name"],
        "role": "Pflege", "department_id": department,
    })
    assert employee.status_code == 201, employee.text
    employee_id = employee.json()["id"]
    # Einladung bei aktivem Mailversand (der Versand schlägt in Tests fehl und wird geloggt).
    invited = client.post("/api/users", headers=admin, json={
        "first_name": "Ein", "last_name": "Geladen", "username": "sentinel.eingeladen",
        "email": SENTINELS["invite_email"], "role_key": "KIOSK", "can_view": True,
    })
    assert invited.status_code == 201, invited.text
    account = client.post("/api/users", headers=admin, json={
        "first_name": SENTINELS["first_name"], "last_name": SENTINELS["last_name"],
        "username": SENTINELS["username"], "password": SENTINELS["password"],
        "role_key": "EMPLOYEE", "department_id": department, "employee_id": employee_id, "can_view": True,
    })
    assert account.status_code == 201, account.text
    planner = client.post("/api/users", headers=admin, json={
        "first_name": "Plan", "last_name": "Person", "username": "datenschutz-planer",
        "password": "Datenschutz-Planer-123", "role_key": "OBERARZT", "department_id": department,
        "can_view": True, "can_edit": True, "can_approve": True,
    })
    assert planner.status_code == 201, planner.text
    planner_headers = _login_headers(client, "datenschutz-planer", "Datenschutz-Planer-123")
    absence = client.post("/api/absences", headers=planner_headers, json={
        "employee_id": employee_id, "kind": "sick", "start_date": "2031-05-05", "end_date": "2031-05-06",
        "note": SENTINELS["absence_note"],
    })
    assert absence.status_code == 201, absence.text
    member = _login_headers(client, SENTINELS["username"], SENTINELS["password"])
    profile = client.put("/api/profile/me", headers=member, json={
        "profile_photo_visibility": "private", "phone": SENTINELS["phone"], "address": SENTINELS["address"],
        "birth_date": "1990-04-03",
    })
    assert profile.status_code == 200, profile.text
    return admin, planner_headers, member, department, employee_id


def test_personal_data_is_never_stored_in_plaintext(client):
    admin, planner, _member, _department, _employee = _create_sentinel_data(client)
    # Die Daten sind über die API lesbar (der Test ist also nicht leer) ...
    assert SENTINELS["first_name"] in json.dumps(client.get("/api/employees", headers=planner).json())
    # ... aber nirgends im Klartext in der Datenbank.
    dump = _dump_raw_database()
    assert "Datenschutz" in dump  # Kontrolle: der Dump enthält unverschlüsselte Organisationsdaten
    for field, value in SENTINELS.items():
        assert value not in dump, f"{field} liegt im Klartext in der Datenbank"
    assert "1990-04-03" not in dump
    assert SENTINELS["last_name"] not in admin.get("Authorization", "")


def test_personal_data_does_not_appear_in_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    _create_sentinel_data(client)
    client.post("/api/auth/login", json={"username": SENTINELS["username"], "password": "falsch-falsch-1"})
    client.post("/api/auth/login", json={"username": "unbekannt", "password": SENTINELS["password"]})
    for field, value in SENTINELS.items():
        assert value not in caplog.text, f"{field} wurde in ein Log geschrieben"


def test_audit_log_contains_no_passwords_or_personal_details(client):
    admin, *_ = _create_sentinel_data(client)
    client.post("/api/auth/login", json={"username": SENTINELS["username"], "password": "falsch-falsch-1"})
    audit = client.get("/api/admin/audit?limit=100", headers=admin)
    assert audit.status_code == 200
    body = json.dumps(audit.json(), ensure_ascii=False)
    for field in ("password", "invite_email", "phone", "address", "absence_note", "first_name", "last_name"):
        assert SENTINELS[field] not in body, f"{field} steht im Audit-Protokoll"
    assert "falsch-falsch-1" not in body


def _keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _keys(nested)


def test_api_responses_never_expose_secrets(client):
    admin, planner, member, _department, _employee = _create_sentinel_data(client)
    responses = [
        ("admin", "/api/users"), ("admin", "/api/employees"), ("admin", "/api/auth/session"),
        ("admin", "/api/admin/mail-settings"), ("admin", "/api/admin/license"),
        ("admin", "/api/admin/security-settings"), ("admin", "/api/profile/me"),
        ("planner", "/api/employees"), ("planner", "/api/absences"), ("planner", "/api/auth/session"),
        ("member", "/api/profile/me"), ("member", "/api/auth/session"),
    ]
    headers = {"admin": admin, "planner": planner, "member": member}
    for role, path in responses:
        response = client.get(path, headers=headers[role])
        assert response.status_code in {200, 403}, f"{path}: {response.status_code}"
        assert not FORBIDDEN_RESPONSE_KEYS & set(_keys(response.json())), f"{path} liefert geheime Felder"
        assert SENTINELS["password"] not in response.text


def test_api_responses_are_not_cacheable(client):
    admin, planner, *_ = _create_sentinel_data(client)
    for path, headers in (
        ("/api/employees", planner), ("/api/absences", planner), ("/api/users", admin),
        ("/api/auth/session", planner), ("/api/profile/me", planner),
    ):
        response = client.get(path, headers=headers)
        assert response.headers.get("cache-control") == "no-store", f"{path} darf nicht gecacht werden"


def test_session_cookie_is_not_readable_by_scripts_or_cross_site(client):
    auth_header(client)
    response = client.post("/api/auth/login", json={"username": "test-admin", "password": "test-password-with-twelve"})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_admin_cannot_read_schedules_or_absences(client):
    admin, *_ = _create_sentinel_data(client)
    assert client.get("/api/absences", headers=admin).status_code == 403
    assert client.get("/api/assignments?from=2031-05-01&to=2031-05-31", headers=admin).status_code == 403


def test_employee_only_sees_own_absences_and_assignments(client):
    admin, planner, member, department, employee_id = _create_sentinel_data(client)
    other = client.post("/api/employees", headers=admin, json={
        "first_name": "Fremd", "last_name": "Person", "role": "Pflege", "department_id": department,
    }).json()["id"]
    assert client.post("/api/absences", headers=planner, json={
        "employee_id": other, "kind": "sick", "start_date": "2031-06-01", "end_date": "2031-06-01",
        "note": "Fremde Sentinel-Notiz",
    }).status_code == 201
    visible = client.get("/api/absences", headers=member)
    assert visible.status_code == 200
    assert {item["employee_id"] for item in visible.json()} == {employee_id}
    assert "Fremde Sentinel-Notiz" not in visible.text
    assert client.get("/api/assignments?from=2031-05-01&to=2031-06-30", headers=member).json() == []


def test_other_departments_cannot_see_employees_or_absence_notes(client):
    admin, planner, _member, _department, _employee = _create_sentinel_data(client)
    other_department = client.post("/api/departments", headers=admin, json={"name": "Fremdabteilung"}).json()["id"]
    assert client.post("/api/users", headers=admin, json={
        "first_name": "Fremd", "last_name": "Planer", "username": "fremd-planer",
        "password": "Fremd-Planer-12345", "role_key": "OBERARZT", "department_id": other_department,
        "can_view": True, "can_edit": True, "can_approve": True,
    }).status_code == 201
    foreign = _login_headers(client, "fremd-planer", "Fremd-Planer-12345")
    for path in ("/api/employees", "/api/absences", "/api/users", "/api/profile/department"):
        response = client.get(path, headers=foreign)
        assert response.status_code in {200, 403}
        for value in SENTINELS.values():
            assert value not in response.text, f"{path} zeigt Daten einer anderen Abteilung"


def _tracked_files() -> list[Path]:
    try:
        output = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git ist nicht verfügbar")
    return [REPO_ROOT / line for line in output.splitlines() if line]


def test_repository_contains_no_secrets_or_data_files():
    files = _tracked_files()
    forbidden_suffixes = (".env", ".pem", ".key", ".sqlite", ".sqlite3", ".db", ".p12", ".pfx")
    allowed = {"backend/app/license_public.pem"}  # öffentlicher Lizenzschlüssel
    tracked = [
        str(path.relative_to(REPO_ROOT)) for path in files
        if (path.name.endswith(forbidden_suffixes) or path.name.startswith(".env"))
        and str(path.relative_to(REPO_ROOT)) not in allowed and not path.name.endswith(".env.example")
    ]
    assert not tracked, f"Geheimnisse oder Datendateien dürfen nicht versioniert werden: {tracked}"

    patterns = [
        re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
        re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ]
    findings = []
    for path in files:
        if path.name in {"package-lock.json", "uv.lock"} or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if path.name == "test_privacy.py":
            continue
        findings.extend(
            f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}" for pattern in patterns if pattern.search(content)
        )
    assert not findings, f"Mögliche Geheimnisse im Repository: {findings}"


def test_browser_storage_holds_only_non_personal_state():
    allowed_keys = {
        "'clinicpulse-theme'",
        "'clinicpulse-sidebar-collapsed'",
        "'clinicpulse-onboarding-mail-skipped'",
        "IDLE_ACTIVITY_STORAGE_KEY",  # Zeitstempel der letzten Aktivität
        "key",  # Hinweisstatus: nur IDs bereits angezeigter Urlaubsanträge
        "storageKey",  # gewählte Sprache
    }
    pattern = re.compile(r"(?:local|session)Storage\.setItem\(\s*([^,)]+?)\s*,")
    found = {}
    for path in (REPO_ROOT / "frontend" / "src").rglob("*"):
        if path.suffix not in {".vue", ".ts"}:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(match.group(1), []).append(path.name)
    unknown = {key: files for key, files in found.items() if key not in allowed_keys}
    assert not unknown, (
        "Neue Browser-Speicherschlüssel müssen datenschutzrechtlich geprüft und hier eingetragen werden: "
        f"{unknown}"
    )
