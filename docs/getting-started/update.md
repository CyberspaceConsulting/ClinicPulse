# ClinicPulse mit Docker aktualisieren

Plane eine kurze Unterbrechung ein und lies vor dem Update die Hinweise zum
neuen Release auf [GitHub Releases](https://github.com/CyberspaceConsulting/ClinicPulse/releases).
Der Update-Hinweis in der Anwendung vergleicht die verfügbaren Backend- und
Web-Images in GitHub Packages; prüfe vor dem Update zusätzlich, ob für den Tag
bereits ein Release mit Compose-Datei, signierter Prüfsummenliste und Signatur-Bundle veröffentlicht wurde.
Erstelle zunächst eine Sicherung und prüfe, ob sie wiederhergestellt werden
kann; siehe [Backup und Wiederherstellung](../features/backup.md). Sichere auch
den vorhandenen Verschlüsselungsschlüssel und deine Konfiguration separat und
geschützt. Ohne den passenden Schlüssel sind verschlüsselte Daten nicht lesbar.

Verwende das Verfahren, das zu deiner Installation passt. Behalte das bestehende
Compose-Projekt, die Volumes, Secrets und Einstellungen bei. Führe insbesondere
kein `docker compose down -v` aus: Dabei werden Compose-Volumes gelöscht.

## Installation aus einem Release aktualisieren

Die Release-Datei `compose.yaml` legt die Image-Versionen fest. Ein bloßes
`docker compose pull` lädt deshalb keine neue ClinicPulse-Version, solange
diese Datei nicht aktualisiert wird.

Beim ersten Wechsel auf ein Release mit verwaltetem Schlüssel-Volume muss der Installer **des neuen Releases** den bisherigen Schlüssel importieren, bevor das Backend startet. Die folgenden manuellen Compose-Schritte allein führen diesen Import nicht aus. Lade Installer, Compose-Datei und Prüfsummen aus demselben Release und verwende das Verfahren unter [Installation](installation.md#release-installieren) mit dem bestehenden Installationsverzeichnis als Ziel. Der Installer behält die Originaldateien; bei abweichenden Schlüsseln im Volume bricht er ab. Nutzt du einen externen Schlüssel, setze `CLINICPULSE_DATA_ENCRYPTION_KEY_FILE` beim Installer-Aufruf auf dessen bisherigen absoluten Pfad. Sichere den Schlüssel vorher und entferne ihn nicht, bis die Wiederherstellung getestet wurde.

Bei bereits eingerichtetem Betrieb mit `compose.external-key.yaml` darf der Installer nicht erneut verwendet werden: Er bricht bewusst ab, um den Schlüssel nicht ins Volume zu kopieren. Stattdessen nach Sicherung die Release-Dateien samt externer Overlay-Datei aus demselben Release laden und deren Prüfsummen prüfen. Danach den entsperrten Speicher und alle bisherigen Compose-Dateien beim manuellen Update beibehalten.

1. Wechsle in das bestehende Installationsverzeichnis, normalerweise
   `clinicpulse`. Sichere eine dort angepasste `compose.yaml` und übertrage
   eigene Änderungen nach dem Download auf die neue Datei. Auch verwendete
   zusätzliche Compose-Dateien, `.env`-Dateien und Einstellungen müssen
   erhalten bleiben; vergleiche sie mit den Hinweisen des neuen Releases.
2. Wähle auf [GitHub Releases](https://github.com/CyberspaceConsulting/ClinicPulse/releases)
   eine Version und ersetze `v-0.2.0-alpha` im folgenden Beispiel durch deren
   Tag. Es gibt derzeit nur Alpha-Vorabversionen; GitHubs `releases/latest`
   liefert diese nicht. Lade Compose-Datei, Prüfsummenliste, Signatur-Bundle und
   Prüfer aus demselben Release. Verifiziere die Signatur und Dateien, bevor du
   die bestehende Datei ersetzt:

   ```sh
   cd clinicpulse
   (
     set -eu
     tmpdir=$(mktemp -d)
     trap 'rm -rf "$tmpdir"' EXIT
     url=https://github.com/CyberspaceConsulting/ClinicPulse/releases/download/v-0.2.0-alpha
       curl -fsSL -o "$tmpdir/compose.yaml" "$url/compose.yaml"
       curl -fsSL -o "$tmpdir/SHA256SUMS" "$url/SHA256SUMS"
       curl -fsSL -o "$tmpdir/SHA256SUMS.sigstore.json" "$url/SHA256SUMS.sigstore.json"
       curl -fsSL -o "$tmpdir/verify-integrity.sh" "$url/verify-integrity.sh"
       (
          cd "$tmpdir"
          cosign verify-blob \
             --bundle SHA256SUMS.sigstore.json \
             --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/ClinicPulse/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
             --certificate-oidc-issuer https://token.actions.githubusercontent.com \
             SHA256SUMS
          awk '$2 == "compose.yaml" || $2 == "verify-integrity.sh" { print; count++ } END { if (count != 2) exit 1 }' SHA256SUMS > assets.sha256
          sha256sum --check assets.sha256
       )
       cp "$tmpdir/compose.yaml" compose.yaml
       cp "$tmpdir/verify-integrity.sh" verify-integrity.sh
       cp "$tmpdir/SHA256SUMS" SHA256SUMS
       cp "$tmpdir/SHA256SUMS.sigstore.json" SHA256SUMS.sigstore.json
       docker compose pull
       docker compose up -d
       sh "$tmpdir/verify-integrity.sh" --release-dir "$tmpdir" --project-dir "$PWD"
   )
   ```

    Bei zusätzlichen Compose-Dateien verwende für `docker compose pull` und
    `docker compose up -d` dieselben `-f`-Optionen wie beim bisherigen Betrieb.
    Übertrage eigene Änderungen in `compose.yaml` nur nach der Signatur- und
    Prüfsummenprüfung. Fahre nur fort, wenn Signatur, Prüfsummen und die
    anschließende Prüfung der laufenden Images erfolgreich sind.

## Datenbankänderungen

Neue Tabellen und Spalten legt das Backend beim Start automatisch an; bestehende
Daten bleiben erhalten. Dazu gehören zuletzt die Zuordnung von Personen zu
weiteren Abteilungen (`employee_department_access`), Fahrzeuge (`vehicles`,
`shift_types.vehicle_id`) und die Begriffs- und Strukturfelder der
Betriebskonfiguration. Eine Rückkehr zur älteren Version nach dem Start der
neuen ist nur mit der zuvor erstellten Sicherung möglich. Bestehende Dienste
werden nicht verändert; neue Zuweisungen verlangen jedoch die passende
Qualifikation, siehe [Dienstplanung](../features/shift-planning.md).

## Installation aus dem Quellcode aktualisieren

Beim ersten Umstieg auf das verwaltete Schlüssel-Volume nicht direkt `docker compose up` verwenden: Führe im Repository `sh deploy/install.sh "$PWD"` aus, wenn die bisherigen Dateien in `./secrets` liegen. Bei einem anderen Installationsziel denselben Zielpfad wie bisher angeben. Der Installer importiert vorhandene Schlüssel vor dem Start.

Im bestehenden Repository-Hauptverzeichnis:

```sh
git status
git pull --ff-only
docker compose -f docker/docker-compose.yml up --build -d
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs --tail=100 backend
```

`git pull --ff-only` aktualisiert den ausgecheckten Branch nur, wenn dies ohne
Merge möglich ist. Kläre lokale Änderungen oder einen fehlgeschlagenen Pull,
bevor du fortfährst. Wenn du ein bestimmtes Release oder einen anderen Branch
verwenden möchtest, prüfe zuerst dessen Release-Hinweise und wechsle bewusst
darauf. Verwende bei eigenen Compose-Dateien oder Einstellungen dieselben
Optionen und Umgebungsvariablen wie bei der ursprünglichen Installation.

Wurde aus dem Checkout mit `deploy/install.sh` installiert, liegen Secrets und
Backups standardmäßig im Zielverzeichnis `clinicpulse`. Führe nach dem
Aktualisieren des Checkouts stattdessen erneut `sh deploy/install.sh
./clinicpulse` aus, damit diese Pfade beim Neubau verwendet werden.

Prüfe anschließend den Status und die Erreichbarkeit der Anwendung. Bei
Problemen helfen die [Fehlerbehebung](../troubleshooting.md) und die zuvor
geprüfte Sicherung. Ein Downgrade ist nach Datenbankänderungen nicht
grundsätzlich sicher; beachte die Hinweise des jeweiligen Releases.
