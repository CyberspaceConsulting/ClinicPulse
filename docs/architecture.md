# Architektur

ClinicPulse besteht aus drei Docker-Compose-Diensten (`docker/docker-compose.yml`):

| Dienst | Aufgabe                                                                  | Netzwerke                 |
| ------ | ------------------------------------------------------------------------ | ------------------------- |
| `web`  | Vue-3-Frontend über nginx; einziger Dienst mit veröffentlichtem Port     | `application`             |
| `api`  | Backend-API (Python), Lizenzprüfung, Planung, Backup                     | `application`, `database` |
| `db`   | PostgreSQL                                                               | `database` (intern)       |

Das Netzwerk `database` ist als `internal` konfiguriert: Die Datenbank ist nicht von außen erreichbar. Sensible Daten werden mit dem Schlüssel aus `secrets/data_encryption_key` verschlüsselt.

## Backend (`backend/app/`)

| Modul                                | Inhalt                                         |
| ------------------------------------ | ---------------------------------------------- |
| `main.py`, `schemas.py`, `models.py` | API, Validierung, Datenmodell (u. a. Mehrfach-Abteilungen, Fahrzeuge) |
| `database.py`, `encrypted.py`        | Datenbankzugriff und Verschlüsselung           |
| `security.py`, `login_throttle.py`   | Authentifizierung, Schutz vor Brute-Force      |
| `role_catalog.py`                    | Rollen, Funktionen und Struktur je Einrichtungsart |
| `absences.py`, `invitations.py`      | Abwesenheiten und Einladungen                  |
| `optimizer.py`, `plan_archive.py`    | Planungsvorschläge und Archiv                  |
| `staffing.py`                        | Qualifikationsabgleich zwischen Personen und Schichtanforderungen |
| `work_rules.py`, `regional_calendar.py` | Arbeits- und Ruhezeitprüfungen, Feiertage   |
| `backup_*.py`                        | Verschlüsselte Sicherung und Wiederherstellung |
| `license_manager.py`, `licensing.py` | Lizenzprüfung                                  |
| `audit.py`, `update_checker.py`      | Protokollierung und Update-Hinweise            |

## Frontend (`frontend/src/`)

Vue 3 mit TypeScript und Vite. Build und Typprüfung: `npm run build`.

## API-Hinweise für Integrationen

Neu oder erweitert (alle Pfade unter `/api`, Authentifizierung wie bei den übrigen Endpunkten; die interaktive Beschreibung liefert `/api/docs`):

| Endpunkt | Änderung |
| -------- | -------- |
| `GET/POST /employees`, `PUT /employees/{id}`, `POST /employees/onboard` | zusätzlich `additional_department_ids` (weitere Abteilungen). `department_id` ist die Hauptabteilung. Antworten blenden Qualifikationen und Zuordnungen anderer Abteilungen aus, auf die das Konto keinen Zugriff hat. |
| `POST /optimization/preview`, `POST /planning/preview` | Vorschläge enthalten zusätzlich `positions` (alle durch die Person abgedeckten Anforderungen); `position` ist die erste davon, `role_match` ist immer `true`. |
| `GET /smart-selection` | nur Personen mit geforderter Qualifikation; Kandidaten enthalten `positions`. |
| `GET /role-catalog` | zusätzlich `structure` (`single_unit`, `uses_vehicles`, `unit_label`, `unit_label_plural`, `unit_gender`, `lead_label`) und `operational_profile`. |
| `GET/PUT /admin/business-configuration` | dieselben Struktur-Felder; bei „Sonstige“ änderbar. |
| `POST /setup` | zusätzlich `unit_name` (Leitstelle bzw. „Sonstige“ mit einer Einheit) sowie bei „Sonstige“ `unit_label`, `unit_label_plural`, `unit_gender`, `lead_label`, `single_unit`, `uses_vehicles`. |
| `GET/POST /vehicles`, `PUT/DELETE /vehicles/{id}` | Fahrzeuge je Standort (`vehicle_type`: RTW, NEF, KTW, ITW, ELW, MTW, Sonstige; `is_active`). Nur wenn die Einrichtungsart Fahrzeuge nutzt (sonst HTTP 409). |
| `POST/PUT /shift-types` | optional `vehicle_id` (Fahrzeug desselben Standorts). |
| `GET /absences` | genehmigte Abwesenheiten von Personen aus der eigenen, aber nicht der Hauptabteilung ohne `note`, `requested_by`, `decided_by` und `decided_at`. |
| alle `/api/*`-Antworten | `Cache-Control: no-store`. |

Geänderte Fehler (HTTP 409): `Employee role is not required for this shift` (Qualifikation fehlt, jetzt für alle Schichten), `Vehicle is deactivated`, `Vehicle is in use`, `This facility type uses a single organizational unit`. Beim Löschen von Abteilungen zählen Fahrzeuge und weitere Zuordnungen als Verwendung.

## Tests

Backend-Tests mit pytest in `tests/backend/`, Browser-Tests mit Playwright in `tests/frontend/`. Siehe [TEST.md](https://github.com/CyberspaceConsulting/ClinicPulse/blob/alpha/TEST.md).
