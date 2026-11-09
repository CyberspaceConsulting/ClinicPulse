# Backup und Wiederherstellung

Sicherungen werden verschlüsselt erstellt und liegen im Verzeichnis `/backups` des API-Containers (Host: `CLINICPULSE_BACKUP_HOST_DIR`, Standard `../backups`). Eine Sicherung kann nur mit dem passenden Wiederherstellungsschlüssel gelesen werden.

Das Kommandozeilenwerkzeug läuft im API-Container und ist für den Umzug auf eine neue Instanz gedacht.

## 1. Neue Instanz: Schlüsselpaar erzeugen

```sh
docker compose exec api python -m app.backup_cli keygen /backups/recovery-key.cpkey
```

Der Befehl gibt den öffentlichen Schlüssel (`CPPUB1:…`) aus und schreibt eine geschützte Schlüsseldatei. Das Passwort der Schlüsseldatei wird aus `CLINICPULSE_KEY_PASSPHRASE` gelesen oder abgefragt.

## 2. Alte Instanz: Sicherung erstellen

```sh
docker compose exec api python -m app.backup_cli export /backups/manual.cpbak --recipient CPPUB1:...
```

## 3. Neue Instanz: Sicherung einspielen

```sh
docker compose exec api python -m app.backup_cli import /backups/manual.cpbak --key /backups/recovery-key.cpkey --yes
```

## Hinweise

- Bewahre die Schlüsseldatei und `secrets/data_encryption_key` getrennt von den Sicherungen auf.
- Teste die Wiederherstellung regelmäßig mit einer entbehrlichen Instanz.
- Verwende für Tests keine echten Personen- oder Gesundheitsdaten.
