# Konfiguration

Die Konfiguration erfolgt über Umgebungsvariablen (siehe `docker/docker-compose.yml`) und Docker-Secrets. Geheimnisse gehören in Dateien unter `secrets/`, nicht in Variablen oder ins Repository.

## Umgebungsvariablen

| Variable                         | Standard                                         | Beschreibung                                               |
| -------------------------------- | ------------------------------------------------ | ---------------------------------------------------------- |
| `CLINICPULSE_PORT`               | `8080`                                           | Port der Weboberfläche                                     |
| `CLINICPULSE_LICENSE_API_URL`    | `https://lic.api.cyberspaceconsulting.de/api/v1` | Adresse des Lizenzdienstes                                 |
| `CLINICPULSE_PUBLIC_URL`         | leer                                             | Öffentliche HTTPS-Adresse, für Links in Einladungen        |
| `CLINICPULSE_SMTP_HOST`          | leer                                             | SMTP-Server (optional)                                     |
| `CLINICPULSE_SMTP_PORT`          | `587`                                            | SMTP-Port                                                  |
| `CLINICPULSE_SMTP_USERNAME`      | leer                                             | SMTP-Benutzer                                              |
| `CLINICPULSE_SMTP_PASSWORD_FILE` | `/run/secrets/smtp_password`                     | Datei mit dem SMTP-Passwort                                |
| `CLINICPULSE_SMTP_FROM`          | leer                                             | Absenderadresse                                            |
| `CLINICPULSE_SMTP_USE_SSL`       | `false`                                          | Implizites TLS                                             |
| `CLINICPULSE_SMTP_USE_STARTTLS`  | `true`                                           | STARTTLS verwenden                                         |
| `CLINICPULSE_BACKUP_HOST_DIR`    | `../backups`                                     | Host-Verzeichnis für Sicherungen (im Container `/backups`) |
| `POSTGRES_PASSWORD`              | leer                                             | Passwort der Datenbank                                     |

## Secrets

| Datei                         | Zweck                                                        |
| ----------------------------- | ------------------------------------------------------------ |
| `secrets/data_encryption_key` | Schlüssel zur Verschlüsselung sensibler Daten (Pflicht)      |
| `secrets/smtp_password`       | SMTP-Passwort (darf leer sein, wenn SMTP nicht genutzt wird) |

Der Schlüssel in `secrets/data_encryption_key` darf nach dem Start nicht verloren gehen oder ausgetauscht werden, sonst sind verschlüsselte Daten nicht mehr lesbar.
