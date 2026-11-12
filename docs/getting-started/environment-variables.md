# Umgebungsvariablen

Die Konfiguration erfolgt über Umgebungsvariablen und ein verwaltetes Schlüssel-Volume. Geheimnisse gehören nicht in Umgebungsvariablen, `.env` oder ins Repository.

## Umgebungsvariablen

| Variable                         | Standard                                         | Beschreibung                                               |
| -------------------------------- | ------------------------------------------------ | ---------------------------------------------------------- |
| `CLINICPULSE_PORT`               | `8080`                                           | Port der Weboberfläche                                     |
| `CLINICPULSE_LICENSE_API_URL`    | `https://lic.api.cyberspaceconsulting.de/api/v1` | Adresse des Lizenzdienstes                                 |
| `CLINICPULSE_PUBLIC_URL`         | leer                                             | Öffentliche HTTPS-Adresse, für Links in Einladungen        |
| `CLINICPULSE_SMTP_HOST`          | leer                                             | SMTP-Server (optional)                                     |
| `CLINICPULSE_SMTP_PORT`          | `587`                                            | SMTP-Port                                                  |
| `CLINICPULSE_SMTP_USERNAME`      | leer                                             | SMTP-Benutzer                                              |
| `CLINICPULSE_SMTP_PASSWORD_FILE` | leer | Optionaler Pfad zu einer bereits im Backend eingebundenen SMTP-Passwortdatei |
| `CLINICPULSE_SMTP_FROM`          | leer                                             | Absenderadresse                                            |
| `CLINICPULSE_SMTP_USE_SSL`       | `false`                                          | Implizites TLS                                             |
| `CLINICPULSE_SMTP_USE_STARTTLS`  | `true`                                           | STARTTLS verwenden                                         |
| `CLINICPULSE_BACKUP_HOST_DIR`    | `../backups`                                     | Host-Verzeichnis für Sicherungen (im Container `/backups`) |
| `CLINICPULSE_DATA_ENCRYPTION_KEY_FILE` | leer | Absoluter Host-Pfad zum bisherigen Schlüssel für den einmaligen Import durch den Installer |
| `CLINICPULSE_SMTP_PASSWORD_SECRET_FILE` | alter Standardpfad unter `secrets/` | Host-Pfad zum bisherigen SMTP-Passwort für den Import durch den Installer |
| `CLINICPULSE_EXTERNAL_KEY_FILE` | leer | Absoluter Host-Pfad zum Schlüssel für `compose.external-key.yaml` |
| `POSTGRES_PASSWORD`              | leer                                             | Passwort der Datenbank                                     |

## Secrets

Bei neuen Installationen mit dieser Funktion erzeugt das Backend den Datenschlüssel automatisch im Docker-Volume `clinicpulse_keys`. Der Schlüssel wird nicht im Installationsverzeichnis angelegt. Bestehende Dateien übernimmt der Installer unverändert und löscht sie nicht. Wenn ein externer Schlüssel über `.env` konfiguriert war, muss dessen Pfad auch beim Installer-Aufruf in der Umgebung gesetzt sein. Siehe [Updates](update.md).

Das Volume ist keine verschlüsselte Schlüsselverwaltung: Root und Personen mit Docker-Zugriff können die Inhalte lesen. Verschlüsselte Host-Datenträger schützen im ausgeschalteten Zustand; Schutz gegenüber Host-Administratoren erfordert ein gesondertes Schlüsselmanagement. Sichere Datenschlüssel und optionales SMTP-Passwort verschlüsselt und getrennt von der Datenbank, siehe [Backup](../features/backup.md#verschlusseltes-schlussel-backup). Ohne den ursprünglichen Schlüssel ist ein roher Datenbank-Dump nicht lesbar.

### Externer Schlüssel auf verschlüsseltem Speicher

Für erhöhten Schutz im ausgeschalteten Zustand kann ein Administrator ein bereits eingerichtetes und entsperrtes verschlüsseltes Dateisystem verwenden, beispielsweise LUKS. ClinicPulse richtet dieses Dateisystem nicht ein und kann nicht überprüfen, ob der angegebene Pfad tatsächlich verschlüsselt ist. Der Schlüssel liegt dort weiterhin als Datei und ist für Root, Docker-Administratoren und den laufenden Backend-Prozess lesbar. Ein kompromittierter laufender Host ist dadurch nicht geschützt.

Verwende `compose.external-key.yaml` aus demselben Release und prüfe seine Prüfsumme gegen dessen `SHA256SUMS`. Diese Funktion ist nicht im alten Beispielrelease `v-0.3.4.1-alpha` enthalten. Der Schlüssel muss bereits vorhanden und mit mindestens 32 zufälligen Bytes in Base64 kodiert sein. Bei einer bestehenden Datenbank unbedingt den **ursprünglichen** Schlüssel verwenden, keinen neuen erzeugen. Das bestehende Volume und bisherige Schlüsseldateien nicht löschen.

Im Release-Installationsverzeichnis, nach dem Entsperren und Prüfen des geschützten Dateisystems:

```sh
export CLINICPULSE_EXTERNAL_KEY_FILE=/mnt/geschuetzt/clinicpulse/data_encryption_key
docker compose -f compose.yaml -f compose.external-key.yaml up -d
```

Das Beispiel gilt nur ohne weitere Compose-Dateien. Verwendete Overrides müssen zusätzlich mit `-f` angegeben werden; dies gilt auch für spätere Start-, Log-, Update- und Backup-Befehle. Der Pfad kann in `.env` gespeichert werden, nicht jedoch der Schlüssel selbst. Das Backend bindet die Datei schreibgeschützt ein. Die Overlay-Datei deaktiviert den automatischen Neustart von Backend und Web: Nach einem Host-Neustart muss das Dateisystem erst entsperrt und überprüft und der Stack danach manuell gestartet werden.

Für den Umstieg eine [verschlüsselte Schlüsselsicherung](../features/backup.md#verschlusseltes-schlussel-backup) erstellen und in ein privates Verzeichnis auf dem entsperrten Dateisystem wiederherstellen. Der bisherige Schlüssel kann weiterhin als Kopie im alten Volume oder in alten Dateien liegen; solange diese Kopien unverschlüsselt bleiben, bieten sie weiterhin einen Angriffspunkt. Erst nach geprüfter Wiederherstellung und separat gesicherter Kopie nach dem eigenen Sicherheitskonzept entfernen. Das Schlüssel-Volume nicht pauschal löschen, da es auch SMTP-Daten enthalten kann.
