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
| `main.py`, `schemas.py`, `models.py` | API, Validierung, Datenmodell                  |
| `database.py`, `encrypted.py`        | Datenbankzugriff und Verschlüsselung           |
| `security.py`, `login_throttle.py`   | Authentifizierung, Schutz vor Brute-Force      |
| `role_catalog.py`                    | Rollen und Funktionen je Einrichtungsart       |
| `absences.py`, `invitations.py`      | Abwesenheiten und Einladungen                  |
| `optimizer.py`, `plan_archive.py`    | Planungsvorschläge und Archiv                  |
| `work_rules.py`, `regional_calendar.py` | Arbeits- und Ruhezeitprüfungen, Feiertage   |
| `backup_*.py`                        | Verschlüsselte Sicherung und Wiederherstellung |
| `license_manager.py`, `licensing.py` | Lizenzprüfung                                  |
| `audit.py`, `update_checker.py`      | Protokollierung und Update-Hinweise            |

## Frontend (`frontend/src/`)

Vue 3 mit TypeScript und Vite. Build und Typprüfung: `npm run build`.

## Tests

Backend-Tests mit pytest in `tests/backend/`, Browser-Tests mit Playwright in `tests/frontend/`. Siehe [TEST.md](https://github.com/CyberspaceConsulting/ClinicPulse/blob/alpha/TEST.md).
