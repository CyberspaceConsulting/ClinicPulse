# Backup und Wiederherstellung

Sicherungen werden verschlüsselt erstellt und liegen im Verzeichnis `/backups` des Backend-Containers (Host: `MEDORA_BACKUP_HOST_DIR`; Standard beim Quellcode-Checkout `../backups`, beim Release `./backups`, jeweils relativ zur Compose-Datei). Eine Sicherung kann nur mit dem passenden Wiederherstellungsschlüssel gelesen werden.

Das Kommandozeilenwerkzeug läuft im Backend-Container und ist für den Umzug auf eine neue Instanz gedacht. Die folgenden Befehle gelten im Repository-Hauptverzeichnis. Bei einer Release-Installation im Installationsverzeichnis stattdessen `docker compose exec backend` ohne `-f docker/docker-compose.yml` verwenden.

Das verschlüsselte Anwendungsbackup enthält die Anwendungsdaten und kann auf einer neuen Instanz mit einem anderen Datenschlüssel eingespielt werden. Ein PostgreSQL-Dump enthält dagegen auch weiterhin verschlüsselte Datenbankfelder und benötigt den ursprünglichen Datenschlüssel. Sichere deshalb zusätzlich das Schlüssel-Volume.

## Sicherungsziele

In der Anwendung konfiguriert der Administrator Sicherungsziele der Art `local`, `sftp`, `webdav` oder `s3`. Ziele lassen sich testen, manuell ausführen und für eine Wiederherstellung auflisten. Automatische Sicherungen benötigen mindestens einen Empfänger-Schlüssel; erzeuge dazu zuerst einen Wiederherstellungsschlüssel. Eine Wiederherstellung über die Oberfläche verlangt die Eingabe von `WIEDERHERSTELLEN`; hochgeladene Dateien sind in der Größe begrenzt.

## Kommandozeile

## 1. Neue Instanz: Schlüsselpaar erzeugen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli keygen /backups/recovery-key.cpkey
```

Der Befehl gibt den öffentlichen Schlüssel (`CPPUB1:…`) aus und schreibt eine geschützte Schlüsseldatei. Das Passwort der Schlüsseldatei wird aus `MEDORA_KEY_PASSPHRASE` gelesen oder abgefragt.

## 2. Alte Instanz: Sicherung erstellen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli export /backups/manual.cpbak --recipient CPPUB1:...
```

## 3. Neue Instanz: Sicherung einspielen

```sh
docker compose -f docker/docker-compose.yml exec backend python -m app.backup_cli import /backups/manual.cpbak --key /backups/recovery-key.cpkey --yes
```

## Verschlüsseltes Schlüssel-Backup

Die folgenden Befehle gelten für Installationen mit dem neuen `medora_keys`-Volume. Ältere Releases verwenden noch `secrets/data_encryption_key`; diese Datei separat geschützt sichern. Im Release-Installationsverzeichnis ein Schlüssel-Backup erzeugen:

```sh
docker compose run --rm --no-deps --entrypoint python backend -m app.managed_secrets export /backups/secret-backup.cpkeys
```

Das Passwort wird zweimal im Terminal abgefragt und muss mindestens 12 Zeichen lang sein. Die Datei enthält den Datenschlüssel und ein optionales SMTP-Passwort, verschlüsselt mit AES-GCM und einem mittels scrypt abgeleiteten Schlüssel. Eine vorhandene Datei wird nicht überschrieben. Das Backup und sein Passwort getrennt und geschützt aufbewahren; nicht in Logs oder Tickets veröffentlichen. Ist `MEDORA_SMTP_PASSWORD_FILE` separat konfiguriert, sichert der Export diese Datei; der Import stellt das Passwort im verwalteten Volume wieder her. Eine abweichende SMTP-Dateikonfiguration muss anschließend bewusst angepasst werden.

Bei Verwendung von `compose.external-key.yaml` muss auch beim Export diese Overlay-Datei zusammen mit allen anderen verwendeten Compose-Dateien angegeben werden. Der Export enthält dann den tatsächlich extern eingebundenen Schlüssel und das verwaltete SMTP-Passwort.

Zur Wiederherstellung zunächst Backend und Web stoppen. Die passende Sicherungsdatei muss unter `/backups` erreichbar sein. Der Import funktioniert auch ohne laufende Datenbank und verweigert das Überschreiben abweichender vorhandener Schlüssel:

```sh
docker compose stop backend web
docker compose run --rm --no-deps --entrypoint python backend -m app.managed_secrets import /backups/secret-backup.cpkeys && \
docker compose up -d backend web
```

Nur nach erfolgreichem Import starten. Bei abweichenden vorhandenen Schlüsseln nicht löschen oder überschreiben, sondern zunächst Ursache und zugehörige Datenbank prüfen. Der Passwortschutz des Schlüssel-Backups und der Wiederherstellungsschlüssel für `.cpbak`-Anwendungsbackups sind voneinander unabhängig.

Ist auf der Wiederherstellungsinstanz bereits ein anderer Datenschlüssel vorhanden, kann ein neues, separates Volume verwendet werden. Dazu eine zusätzliche Compose-Datei `compose.recovery.yaml` mit einem **noch nicht verwendeten**, individuell gewählten Volumenamen anlegen:

```yaml
volumes:
  medora_keys:
    name: medora-recovery-keys-UNIQUE
```

Die Datei muss bei **allen** Compose-Befehlen zusätzlich zu sämtlichen bisher verwendeten Compose-Dateien angegeben werden. Für eine Release-Installation ohne weitere Overrides beispielsweise:

```sh
docker compose -f compose.yaml -f compose.recovery.yaml run --rm --no-deps --entrypoint python backend -m app.managed_secrets import /backups/secret-backup.cpkeys && \
docker compose -f compose.yaml -f compose.recovery.yaml up -d backend web
```

Vor dem Start die passende Datenbank wiederherstellen und prüfen, dass der Import erfolgreich war. Bei bereits verwendeten Overrides müssen diese ebenfalls mit `-f` angegeben werden; sie dürfen nicht übergangen werden. Das bisherige Schlüssel-Volume bleibt erhalten. Die Recovery-Datei und die vollständige Compose-Konfiguration müssen auch für spätere Neustarts erhalten bleiben.

### Externen Schlüssel wiederherstellen

Zuerst Backend und Web stoppen. Das Zielverzeichnis muss bereits existieren, Modus `700` haben und auf dem **entsperrten, überprüften verschlüsselten Dateisystem** liegen. Das folgende Beispiel gilt nur für eine Release-Installation ohne weitere Overrides; andernfalls alle bisherigen Compose-Dateien mit `-f` ergänzen. Für den Import die externe Schlüssel-Overlay-Datei noch nicht einbinden, wenn die Schlüsseldatei fehlt:

```sh
docker compose -f compose.yaml stop backend web
test -d /mnt/geschuetzt/medora && \
docker compose -f compose.yaml run --rm --no-deps \
	--volume /mnt/geschuetzt/medora:/run/key-recovery \
	--entrypoint python backend -m app.managed_secrets import \
	/backups/secret-backup.cpkeys --key-directory /run/key-recovery
```

Der Import erzeugt `data_encryption_key` im Zielverzeichnis und stellt das optionale SMTP-Passwort im verwalteten Volume wieder her. Abweichende vorhandene Dateien werden nicht überschrieben. Der Container kann die neue Schlüsseldatei als Root anlegen. Das `test -d` bestätigt nur, dass das Verzeichnis existiert, nicht dass es verschlüsselt oder korrekt eingehängt ist. Erst nach erfolgreichem Import und Prüfung mit der [externen Schlüsselkonfiguration](../getting-started/environment-variables.md#externer-schlussel-auf-verschlusseltem-speicher) starten.

## PostgreSQL-Datenbank sichern

Für eine zusätzliche technische Sicherung im Release-Installationsverzeichnis:

```sh
umask 077
docker compose exec -T db pg_dump -Fc -U medora -d medora > medora-db.dump && \
docker compose exec -T db pg_restore --list < medora-db.dump > /dev/null
```

`pg_dump` erzeugt einen konsistenten Dump, verschlüsselt die gesamte Datei aber **nicht**. Sie kann sensible Daten enthalten und muss auf verschlüsseltem Speicher geschützt werden. Die zweite Zeile prüft nur das Archivverzeichnis und ersetzt keinen Wiederherstellungstest. Für eine vollständige Wiederherstellung werden der zu diesem Datenbankstand passende Datenschlüssel und die Konfiguration benötigt.

Einen Dump nur in eine **leere, eigens dafür vorbereitete** Datenbank einspielen, während das Backend gestoppt ist. Beispiel für eine leere Datenbank `medora` im bereits gestarteten `db`-Dienst:

```sh
docker compose stop backend web
docker compose exec -T db pg_restore --exit-on-error --no-owner --no-acl -U medora -d medora < medora-db.dump
```

Anschließend den passenden Datenschlüssel wie oben wiederherstellen und erst dann Backend und Web starten. Der Befehl löscht keine vorhandenen Tabellen und ist kein Ersatz für ein geprüftes Wiederherstellungskonzept.

## Hinweise

- Bewahre Wiederherstellungsschlüssel, Schlüssel-Backup und Passwörter geschützt und getrennt von den Datenbanksicherungen auf.
- Teste die Wiederherstellung regelmäßig mit einer entbehrlichen Instanz.
- Verwende für Tests keine echten Personen- oder Gesundheitsdaten.
