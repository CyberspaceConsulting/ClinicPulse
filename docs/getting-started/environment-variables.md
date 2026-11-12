# Umgebungsvariablen

Die Konfiguration erfolgt über Umgebungsvariablen und dateibasierte Compose-Secrets. Geheimnisse gehören nicht in Umgebungsvariablen, `.env` oder ins Repository.

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
| `CLINICPULSE_DATA_ENCRYPTION_KEY_FILE` | Standardpfad unter `secrets/` | Absoluter Host-Pfad zu einem bestehenden Datenverschlüsselungsschlüssel |
| `CLINICPULSE_SMTP_PASSWORD_SECRET_FILE` | Standardpfad unter `secrets/` | Host-Pfad zur SMTP-Passwortdatei für Compose |
| `POSTGRES_PASSWORD`              | leer                                             | Passwort der Datenbank                                     |

## Secrets

| Datei                         | Zweck                                                        |
| ----------------------------- | ------------------------------------------------------------ |
| `secrets/data_encryption_key` | Schlüssel zur Verschlüsselung sensibler Daten (Pflicht)      |
| `secrets/smtp_password`       | SMTP-Passwort (darf leer sein, wenn SMTP nicht genutzt wird) |

Der Schlüssel in `secrets/data_encryption_key` darf nach dem Start nicht verloren gehen oder ausgetauscht werden, sonst sind verschlüsselte Daten nicht mehr lesbar.

### Extern verwalteter Schlüssel

Ab einem Release mit dieser Funktion kann der Datenverschlüsselungsschlüssel außerhalb des Installationsverzeichnisses auf einem separat geschützten, beispielsweise verschlüsselten und entsperrten Dateisystem liegen. Er muss eine bestehende Datei mit mindestens 32 zufälligen Bytes in Base64-Kodierung sein. Beim Installer den absoluten Pfad über `CLINICPULSE_DATA_ENCRYPTION_KEY_FILE` setzen; die Datei wird nicht erzeugt oder verändert. Für spätere Compose-Aufrufe denselben Pfad in der `clinicpulse/.env` hinterlegen, zum Beispiel:

```dotenv
CLINICPULSE_DATA_ENCRYPTION_KEY_FILE=/geschuetzter/speicher/clinicpulse-key
```

Beim Umstellen einer bestehenden Installation muss dieselbe Schlüsseldatei sicher kopiert und separat gesichert werden. Keinen neuen Schlüssel erzeugen. Das geschützte Dateisystem muss vor dem Start verfügbar sein. Der Installer verwendet die Umgebungsvariable auch bei erneutem Aufruf; setze sie daher dort ebenfalls.

Dateibasierte Compose-Secrets sind auf dem Host nicht automatisch verschlüsselt. Der Standard-Installer schützt sein Verzeichnis mit Modus `700` und die Dateien mit `600`; Root und Personen mit Zugriff auf den Docker-Daemon können dennoch an Schlüssel gelangen. Ein separates verschlüsseltes Dateisystem schützt vor Zugriff auf ausgeschaltete Datenträger, nicht vor einem kompromittierten laufenden Host. Schutz vor Host-Administratoren erfordert eine externe Schlüsselverwaltung und ein passendes Betriebskonzept.
