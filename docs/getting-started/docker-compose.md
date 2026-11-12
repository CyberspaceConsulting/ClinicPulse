# Docker Compose

Die Datei `docker/docker-compose.yml` definiert drei Dienste. Starte sie aus dem Repository-Hauptverzeichnis mit `-f docker/docker-compose.yml`.

## Dienste

| Dienst | Image / Build                       | Aufgabe                                      |
| ------ | ----------------------------------- | -------------------------------------------- |
| `db`   | `postgres:18-alpine`                | PostgreSQL-Datenbank, Healthcheck mit `pg_isready` |
| `backend` | `backend/Dockerfile` | Backend-API; startet erst, wenn `db` gesund ist |
| `web`  | `docker/web.Dockerfile` (`frontend/`) | Frontend mit nginx; veröffentlicht Port `${CLINICPULSE_PORT:-8080}` |

Alle Dienste starten mit `restart: unless-stopped`.

## Netzwerke

- `database` ist `internal`: Nur `db` und `backend` sind darin, die Datenbank ist von außen nicht erreichbar.
- `application` verbindet `web` und `backend`.

## Volumes

| Volume / Pfad                                   | Inhalt                                              |
| ----------------------------------------------- | --------------------------------------------------- |
| `clinicpulse_data`                              | PostgreSQL-Daten                                    |
| `clinicpulse_keys`                              | Verwalteter Datenschlüssel und optionales SMTP-Passwort |
| `${CLINICPULSE_BACKUP_HOST_DIR:-../backups}`    | Sicherungen, im API-Container unter `/backups`      |

## Schlüsselverwaltung

Das Backend erzeugt den Datenschlüssel bei einer leeren Datenbank automatisch im separaten Volume `clinicpulse_keys`. Bei einer vorhandenen Datenbank ohne Schlüssel verweigert es den Start. Das Volume ist nicht automatisch verschlüsselt; Docker- und Host-Administratoren können darauf zugreifen. Sichere den Schlüssel wie unter [Backup und Wiederherstellung](../features/backup.md#verschlusseltes-schlussel-backup) beschrieben.

## Weitere Compose-Dateien

`docker/compose.release.yaml` und `docker/compose.encrypted.yaml` ergänzen den Betrieb mit Release-Images bzw. verschlüsseltem Datenverzeichnis (`CLINICPULSE_ENCRYPTED_PGDATA`). `docker/compose.external-key.yaml` bindet einen [extern verwalteten Schlüssel](environment-variables.md#externer-schlussel-auf-verschlusseltem-speicher) schreibgeschützt ein.

## Befehle

```sh
docker compose -f docker/docker-compose.yml up --build -d   # starten
docker compose -f docker/docker-compose.yml ps              # Status
docker compose -f docker/docker-compose.yml logs -f backend # Logs eines Dienstes
docker compose -f docker/docker-compose.yml down            # stoppen (Daten bleiben im Volume erhalten)
```

Für Versionswechsel siehe die [Update-Anleitung](update.md).
