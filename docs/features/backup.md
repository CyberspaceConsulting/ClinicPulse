# Backup und Wiederherstellung

Sicherungen werden verschlüsselt erstellt und liegen im Verzeichnis `/backups` des Backend-Containers (Host: `CLINICPULSE_BACKUP_HOST_DIR`; Standard beim Quellcode-Checkout `../backups`, beim Release `./backups`, jeweils relativ zur Compose-Datei). Eine Sicherung kann nur mit dem passenden Wiederherstellungsschlüssel gelesen werden.

Das Kommandozeilenwerkzeug läuft im Backend-Container und ist für den Umzug auf eine neue Instanz gedacht. Die folgenden Befehle gelten im Repository-Hauptverzeichnis. Bei einer Release-Installation im Installationsverzeichnis stattdessen `docker compose exec backend` ohne `-f docker/docker-compose.yml` verwenden.

## Sicherungsziele

In der Anwendung konfiguriert der Administrator Sicherungsziele der Art `local`, `sftp`, `webdav` oder `s3`. Ziele lassen sich testen, manuell ausführen und für eine Wiederherstellung auflisten. Automatische Sicherungen benötigen mindestens einen Empfänger-Schlüssel; erzeuge dazu zuerst einen Wiederherstellungsschlüssel. Eine Wiederherstellung über die Oberfläche verlangt die Eingabe von `WIEDERHERSTELLEN`; hochgeladene Dateien sind in der Größe begrenzt.

## Kommandozeile

## 1. Neue Instanz: Schlüsselpaar erzeugen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli keygen /backups/recovery-key.cpkey
```

Der Befehl gibt den öffentlichen Schlüssel (`CPPUB1:…`) aus und schreibt eine geschützte Schlüsseldatei. Das Passwort der Schlüsseldatei wird aus `CLINICPULSE_KEY_PASSPHRASE` gelesen oder abgefragt.

## 2. Alte Instanz: Sicherung erstellen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli export /backups/manual.cpbak --recipient CPPUB1:...
```

## 3. Neue Instanz: Sicherung einspielen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli import /backups/manual.cpbak --key /backups/recovery-key.cpkey --yes
```

## Hinweise

- Bewahre die Schlüsseldatei und `secrets/data_encryption_key` getrennt von den Sicherungen auf.
- Teste die Wiederherstellung regelmäßig mit einer entbehrlichen Instanz.
- Verwende für Tests keine echten Personen- oder Gesundheitsdaten.
