# ClinicPulse mit Docker aktualisieren

Plane eine kurze Unterbrechung ein und lies vor dem Update die Hinweise zum
neuen Release auf [GitHub Releases](https://github.com/CyberspaceConsulting/ClinicPulse/releases).
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

1. Wechsle in das bestehende Installationsverzeichnis, normalerweise
   `clinicpulse`. Sichere eine dort angepasste `compose.yaml` und übertrage
   eigene Änderungen nach dem Download auf die neue Datei. Auch verwendete
   zusätzliche Compose-Dateien, `.env`-Dateien und Einstellungen müssen
   erhalten bleiben; vergleiche sie mit den Hinweisen des neuen Releases.
2. Wähle auf [GitHub Releases](https://github.com/CyberspaceConsulting/ClinicPulse/releases)
   eine Version und ersetze `v-0.2.0-alpha` im folgenden Beispiel durch deren
   Tag. Es gibt derzeit nur Alpha-Vorabversionen; GitHubs `releases/latest`
   liefert diese nicht. Lade die Compose-Datei und ihre Prüfsumme aus demselben
   Release herunter und prüfe sie, bevor du die bestehende Datei ersetzt:

   ```sh
   cd clinicpulse
   (
     set -eu
     tmpdir=$(mktemp -d)
     trap 'rm -rf "$tmpdir"' EXIT
     url=https://github.com/CyberspaceConsulting/ClinicPulse/releases/download/v-0.2.0-alpha
     curl -fsSL -o "$tmpdir/compose.yaml" "$url/compose.yaml"
     curl -fsSL -o "$tmpdir/SHA256SUMS" "$url/SHA256SUMS"
     (
       cd "$tmpdir"
       awk '$2 == "compose.yaml" { print; count++ } END { if (count != 1) exit 1 }' SHA256SUMS > compose.sha256
       sha256sum --check compose.sha256
     )
     cp "$tmpdir/compose.yaml" compose.yaml
   )
   ```

   Fahre nur fort, wenn der Download und die Prüfsummenprüfung erfolgreich
   waren.
   Übertrage gegebenenfalls deine eigenen Änderungen in die neue
   `compose.yaml`, bevor du die Dienste aktualisierst.
3. Lade die Images und starte die Dienste mit der neuen Konfiguration:

   ```sh
   docker compose pull
   docker compose up -d
   docker compose ps
   docker compose logs --tail=100 backend
   ```

   Bei zusätzlichen Compose-Dateien verwende dieselben `-f`-Optionen und
   Umgebungsvariablen wie beim bisherigen Betrieb. Prüfe, ob die Dienste laufen
   und die Anwendung erreichbar ist.

## Installation aus dem Quellcode aktualisieren

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
