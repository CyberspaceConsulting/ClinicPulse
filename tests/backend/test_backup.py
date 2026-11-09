import base64
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app import backup_core, models
from app.backup_api import latest_slot, run_due_backup
from app.backup_core import BackupError
from app.database import SessionLocal
from test_api import auth_header

KEY_PASSPHRASE = "key-file-passphrase-123"
CONFIRM = "WIEDERHERSTELLEN"


def _recovery_key(client, headers, name="Diese Instanz", add=True):
    response = client.post(
        "/api/admin/backup/recovery-key",
        json={"name": name, "passphrase": KEY_PASSPHRASE, "add_as_recipient": add},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.headers["x-public-key"], response.content


def _seed(client, headers):
    department_id = client.post("/api/departments", json={"name": "General"}, headers=headers).json()["id"]
    employee = client.post(
        "/api/employees",
        json={"first_name": "Alex", "last_name": "Beispiel", "role": "Nurse", "department_id": department_id},
        headers=headers,
    )
    assert employee.status_code == 201
    with SessionLocal() as db:
        db.add(models.ShiftType(name="Früh", start_time=time(7, 0), end_time=time(15, 30), position="Nurse", required_staff=1, department_id=department_id))
        db.commit()
    return employee.json()["id"]


def _employee_names(client, headers):
    return sorted(item["name"] for item in client.get("/api/employees", headers=headers).json())


def _wipe(client, headers):
    for item in client.get("/api/employees", headers=headers).json():
        client.delete(f"/api/employees/{item['id']}", headers=headers)
    with SessionLocal() as db:
        db.query(models.ShiftType).delete()
        db.commit()


def _restore_headers(headers, key_file, passphrase=KEY_PASSPHRASE, confirm=CONFIRM):
    return {
        **headers,
        "X-Recovery-Key": base64.b64encode(key_file).decode(),
        "X-Key-Passphrase": passphrase,
        "X-Restore-Confirm": confirm,
        "Content-Type": "application/octet-stream",
    }


def test_encryption_is_only_readable_with_the_matching_private_key():
    public_a, file_a = backup_core.generate_recovery_key(KEY_PASSPHRASE)
    public_b, file_b = backup_core.generate_recovery_key(KEY_PASSPHRASE)
    blob = backup_core.encrypt_payload({"format": 1, "tables": {}}, [public_a])
    assert backup_core.decrypt_payload(blob, backup_core.load_recovery_key(file_a, KEY_PASSPHRASE))["format"] == 1
    with pytest.raises(BackupError, match="nicht für diese Instanz"):
        backup_core.decrypt_payload(blob, backup_core.load_recovery_key(file_b, KEY_PASSPHRASE))
    with pytest.raises(BackupError):
        backup_core.load_recovery_key(file_a, "wrong key passphrase")
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(BackupError):
        backup_core.decrypt_payload(tampered, backup_core.load_recovery_key(file_a, KEY_PASSPHRASE))
    both = backup_core.encrypt_payload({"format": 1, "tables": {}}, [public_a, public_b])
    for key_file in (file_a, file_b):
        assert backup_core.decrypt_payload(both, backup_core.load_recovery_key(key_file, KEY_PASSPHRASE))["format"] == 1
    with pytest.raises(BackupError):
        backup_core.encrypt_payload({}, [])
    with pytest.raises(BackupError):
        backup_core.encrypt_payload({}, ["CPPUB1:invalid"])
    with pytest.raises(BackupError):
        backup_core.generate_recovery_key("short")


def test_backup_for_another_instance_roundtrip_with_time_columns(client):
    headers = auth_header(client)
    _seed(client, headers)
    # The "new instance" creates its own key; the old instance encrypts only for it.
    new_public, new_key_file = backup_core.generate_recovery_key(KEY_PASSPHRASE)
    response = client.post("/api/admin/backup/download", json={"public_key": new_public}, headers=headers)
    assert response.status_code == 200
    assert b"Alex Beispiel" not in response.content
    backup = response.content

    _wipe(client, headers)
    assert _employee_names(client, headers) == []
    restored = client.post("/api/admin/backup/restore", content=backup, headers=_restore_headers(headers, new_key_file))
    assert restored.status_code == 200, restored.text
    assert _employee_names(client, headers) == ["Alex Beispiel"]
    with SessionLocal() as db:
        shifts = db.query(models.ShiftType).all()
        assert [(item.name, item.start_time, item.end_time) for item in shifts] == [("Früh", time(7, 0), time(15, 30))]
    assert client.post("/api/auth/login", json={"username": "test-admin", "password": "test-password-with-twelve"}).status_code == 200
    with SessionLocal() as db:
        assert db.query(models.AuditEvent).filter_by(action="restored").count() == 1


def test_restore_rejects_bad_requests_without_changing_data(client):
    headers = auth_header(client)
    _seed(client, headers)
    own_public, own_key_file = _recovery_key(client, headers)
    other_public, other_key_file = backup_core.generate_recovery_key(KEY_PASSPHRASE)
    backup = client.post("/api/admin/backup/download", json={}, headers=headers).content
    url = "/api/admin/backup/restore"
    assert client.post(url, content=backup, headers=_restore_headers(headers, own_key_file, confirm="")).status_code == 422
    assert client.post(url, content=backup, headers=_restore_headers(headers, own_key_file, passphrase="wrong wrong wrong")).status_code == 422
    assert client.post(url, content=backup, headers=_restore_headers(headers, other_key_file)).status_code == 422
    assert client.post(url, content=b"garbage", headers=_restore_headers(headers, own_key_file)).status_code == 422
    assert client.post(url, content=backup, headers={**headers, "X-Restore-Confirm": CONFIRM}).status_code == 422
    assert _employee_names(client, headers) == ["Alex Beispiel"]


def test_backup_requires_recipient_and_admin(client):
    assert client.get("/api/admin/backup/settings").status_code == 401
    assert client.post("/api/admin/backup/download", json={}).status_code == 401
    headers = auth_header(client)
    assert client.post("/api/admin/backup/download", json={}, headers=headers).status_code == 422
    schedule = {"schedule_enabled": True, "frequency": "weekly", "weekday": 6, "time_of_day": "03:00"}
    assert client.put("/api/admin/backup/settings", json=schedule, headers=headers).status_code == 422
    public_key, _ = _recovery_key(client, headers)
    assert client.get("/api/admin/backup/recipients", headers=headers).json()[0]["public_key"] == public_key
    assert client.put("/api/admin/backup/settings", json=schedule, headers=headers).status_code == 200
    assert client.post("/api/admin/backup/recipients", json={"name": "x", "public_key": "nope"}, headers=headers).status_code == 422
    assert client.post("/api/admin/backup/recipients", json={"name": "Dup", "public_key": public_key}, headers=headers).status_code == 409


def test_local_target_run_retention_and_restore(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CLINICPULSE_BACKUP_DIR", str(tmp_path))
    headers = auth_header(client)
    _seed(client, headers)
    _, key_file = _recovery_key(client, headers)
    created = client.post(
        "/api/admin/backup/targets",
        json={"name": "Lokal", "kind": "local", "config": {"subdir": "weekly"}, "retention_count": 2},
        headers=headers,
    )
    assert created.status_code == 201
    target_id = created.json()["id"]
    assert client.post(f"/api/admin/backup/targets/{target_id}/test", headers=headers).status_code == 200

    for index in range(3):
        monkeypatch.setattr("app.backup_api.backup_filename", lambda i=index: f"clinicpulse-20260101-00000{i}.cpbak")
        run = client.post(f"/api/admin/backup/targets/{target_id}/run", headers=headers)
        assert run.status_code == 200 and run.json()["status"] == "success", run.text
    files = client.get(f"/api/admin/backup/targets/{target_id}/files", headers=headers).json()
    assert [item["name"] for item in files] == ["clinicpulse-20260101-000002.cpbak", "clinicpulse-20260101-000001.cpbak"]
    assert (tmp_path / "weekly" / files[0]["name"]).stat().st_mode & 0o777 == 0o600
    assert b"Alex Beispiel" not in (tmp_path / "weekly" / files[0]["name"]).read_bytes()
    assert len(client.get("/api/admin/backup/runs", headers=headers).json()) == 3

    _wipe(client, headers)
    body = {"filename": files[0]["name"], "recovery_key": key_file.decode(), "key_passphrase": KEY_PASSPHRASE, "confirm": CONFIRM}
    assert client.post(f"/api/admin/backup/targets/{target_id}/restore", json={**body, "key_passphrase": "wrong wrong wrong"}, headers=headers).status_code == 422
    restored = client.post(f"/api/admin/backup/targets/{target_id}/restore", json=body, headers=headers)
    assert restored.status_code == 200, restored.text
    assert _employee_names(client, headers) == ["Alex Beispiel"]


def test_target_validation_masks_secrets_and_blocks_traversal(client, monkeypatch, tmp_path):
    monkeypatch.setenv("CLINICPULSE_BACKUP_DIR", str(tmp_path))
    headers = auth_header(client)
    traversal = client.post("/api/admin/backup/targets", json={"name": "x", "kind": "local", "config": {"subdir": "../etc"}}, headers=headers)
    assert traversal.status_code == 422
    fingerprint = "SHA256:" + "A" * 43
    created = client.post(
        "/api/admin/backup/targets",
        json={"name": "NAS", "kind": "sftp", "config": {"host": "nas.local", "username": "backup", "password": "geheim", "host_key_fingerprint": fingerprint}},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["config"]["password"] == "********"
    updated = client.put(
        f"/api/admin/backup/targets/{created.json()['id']}",
        json={"name": "NAS", "kind": "sftp", "config": {**created.json()["config"], "directory": "/backups"}},
        headers=headers,
    )
    assert updated.status_code == 200
    with SessionLocal() as db:
        import json
        assert json.loads(db.get(models.BackupTarget, created.json()["id"]).config)["password"] == "geheim"
    for kind, config in (("webdav", {"url": "http://cloud.example.org/dav"}), ("s3", {"endpoint_url": "http://s3.example.org", "bucket": "b", "access_key": "a", "secret_key": "s"})):
        insecure = client.post("/api/admin/backup/targets", json={"name": f"plain-{kind}", "kind": kind, "config": config}, headers=headers)
        assert insecure.status_code == 422 and "https://" in insecure.json()["detail"]
    assert client.post("/api/admin/backup/targets", json={"name": "ok", "kind": "webdav", "config": {"url": "https://cloud.example.org/dav"}}, headers=headers).status_code == 201
    assert client.post("/api/admin/backup/targets", json={"name": "bad", "kind": "sftp", "config": {"host": "h", "username": "u", "password": "p", "host_key_fingerprint": "nope"}}, headers=headers).status_code == 422


def test_schedule_slots_and_due_run(client, monkeypatch, tmp_path):
    zone = ZoneInfo("Europe/Berlin")
    sunday_noon = datetime(2026, 11, 8, 12, 0, tzinfo=zone)
    assert latest_slot(sunday_noon, "weekly", 6, "03:00") == datetime(2026, 11, 8, 3, 0, tzinfo=zone)
    assert latest_slot(datetime(2026, 11, 8, 2, 0, tzinfo=zone), "weekly", 6, "03:00") == datetime(2026, 11, 1, 3, 0, tzinfo=zone)
    assert latest_slot(datetime(2026, 11, 8, 2, 0, tzinfo=zone), "daily", 0, "03:00") == datetime(2026, 11, 7, 3, 0, tzinfo=zone)

    monkeypatch.setenv("CLINICPULSE_BACKUP_DIR", str(tmp_path))
    headers = auth_header(client)
    _seed(client, headers)
    assert client.post("/api/admin/backup/targets", json={"name": "Lokal", "kind": "local", "config": {}}, headers=headers).status_code == 201
    _recovery_key(client, headers)
    assert client.put(
        "/api/admin/backup/settings",
        json={"schedule_enabled": True, "frequency": "daily", "weekday": 0, "time_of_day": "03:00"},
        headers=headers,
    ).status_code == 200
    with SessionLocal() as db:
        assert run_due_backup(db) == []  # slot before saving the schedule is not run retroactively
        settings = db.get(models.BackupSettings, 1)
        settings.last_slot = None
        db.commit()
        runs = run_due_backup(db)
        assert [run.status for run in runs] == ["success"]
        assert run_due_backup(db) == []  # the same slot is never run twice
    assert len(list(tmp_path.glob("clinicpulse-*.cpbak"))) == 1
