# Docker Compose

Die Datei `docker/docker-compose.yml` definiert drei Dienste. Pfade wie `../secrets` sind relativ zu dieser Datei; starte sie daher aus dem Repository-Hauptverzeichnis mit `-f docker/docker-compose.yml`.

## Dienste

| Dienst | Image / Build                       | Aufgabe                                      |
| ------ | ----------------------------------- | -------------------------------------------- |
| `db`   | `postgres:18-alpine`                | PostgreSQL-Datenbank, Healthcheck mit `pg_isready` |
| `backend` | `docker/api.Dockerfile` (`backend/`) | Backend-API; startet erst, wenn `db` gesund ist |
| `web`  | `docker/web.Dockerfile` (`frontend/`) | Frontend mit nginx; veröffentlicht Port `${CLINICPULSE_PORT:-8080}` |

Alle Dienste starten mit `restart: unless-stopped`.

## Netzwerke

- `database` ist `internal`: Nur `db` und `backend` sind darin, die Datenbank ist von außen nicht erreichbar.
- `application` verbindet `web` und `backend`.

## Volumes

| Volume / Pfad                                   | Inhalt                                              |
| ----------------------------------------------- | --------------------------------------------------- |
| `clinicpulse_data`                              | PostgreSQL-Daten                                    |
| `${CLINICPULSE_BACKUP_HOST_DIR:-../backups}`    | Sicherungen, im API-Container unter `/backups`      |

## Secrets

| Secret                            | Quelle                                                  |
| --------------------------------- | ------------------------------------------------------- |
| `clinicpulse_data_encryption_key` | `${CLINICPULSE_DATA_ENCRYPTION_KEY_FILE:-../secrets/data_encryption_key}` |
| `smtp_password`                   | `../secrets/smtp_password`                              |

Die Secrets werden als Dateien unter `/run/secrets/` in den API-Container eingebunden.

## Weitere Compose-Dateien

`docker/compose.release.yaml` und `docker/compose.encrypted.yaml` ergänzen den Betrieb mit Release-Images bzw. verschlüsseltem Datenverzeichnis (`CLINICPULSE_ENCRYPTED_PGDATA`).

## Befehle

```sh
docker compose -f docker/docker-compose.yml up --build -d   # starten
docker compose -f docker/docker-compose.yml ps              # Status
docker compose -f docker/docker-compose.yml logs -f backend # Logs eines Dienstes
docker compose -f docker/docker-compose.yml down            # stoppen (Daten bleiben im Volume erhalten)
```

Für Versionswechsel siehe die [Update-Anleitung](update.md).
