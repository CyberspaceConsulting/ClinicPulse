# Installation

ClinicPulse wird als Release mit Docker Compose gestartet. Weboberfläche, API und PostgreSQL laufen dabei in getrennten Containern.

## Voraussetzungen

- Docker Engine mit Docker Compose v2
- `curl`, `openssl` und `sha256sum`
- Ein gültiger Lizenzzugang und ausgehender HTTPS-Zugriff des Backends auf den Lizenzdienst

## Release installieren

Wähle ein Release auf [GitHub Releases](https://github.com/CyberspaceConsulting/ClinicPulse/releases) und ersetze den Tag im Beispiel. Das Skript prüft die Prüfsummen von Installer und Compose-Datei und installiert nach `./clinicpulse`. Alpha-Releases werden von GitHubs `releases/latest` nicht erfasst.

Bei einem Update mit bestehender Datenbank kann `v-0.3.4.1-alpha` beim Start scheitern; siehe [Fehlerbehebung](../troubleshooting.md#fehlende-fahrzeugspalte-beim-start).

```sh
(
  set -eu
  target="$(pwd)/clinicpulse"
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  url=https://github.com/CyberspaceConsulting/ClinicPulse/releases/download/v-0.3.4.1-alpha
  curl -fsSL -o "$tmpdir/install.sh" "$url/install.sh"
  curl -fsSL -o "$tmpdir/compose.yaml" "$url/compose.yaml"
  curl -fsSL -o "$tmpdir/SHA256SUMS" "$url/SHA256SUMS"
  cd "$tmpdir"
  awk '$2 == "install.sh" { install++; print } $2 == "compose.yaml" { compose++; print } END { if (install != 1 || compose != 1) exit 1 }' SHA256SUMS > install.sha256
  sha256sum --check install.sha256
  sh ./install.sh "$target"
)
```

Öffne anschließend `http://localhost:8080` und lege bei der [Ersteinrichtung](first-setup.md) Lizenz und Administrator an.

::: warning Schlüssel sichern
Sichere den Datenverschlüsselungsschlüssel getrennt von der Datenbank. Ohne den ursprünglichen Schlüssel sind verschlüsselte Daten nicht wiederherstellbar. Beachte die [Hinweise zu Secrets](environment-variables.md#secrets).
:::

## Volumes und Verzeichnisse

| Speicher | Zweck |
| --- | --- |
| Docker-Volume `clinicpulse_data` | PostgreSQL-Datenbank |
| `clinicpulse/backups` | Verschlüsselte Anwendungssicherungen |
| `clinicpulse/secrets` | Standardpfad für Schlüssel und optionales SMTP-Passwort |

Die Datenbank bleibt beim Neustart und Update erhalten. Lösche das Volume nicht, solange Daten benötigt werden.

## Anderer Port

Setze vor der Installation `CLINICPULSE_PORT`, zum Beispiel `export CLINICPULSE_PORT=9090`. Damit spätere Compose-Aufrufe denselben Port verwenden, trage `CLINICPULSE_PORT=9090` in `clinicpulse/.env` ein. Die Anwendung ist dann unter `http://localhost:9090` erreichbar.

## Updates

Release-Images sind versionsgebunden. Ein `docker compose pull` allein wechselt nicht auf eine neue Version. Sichere Daten und Schlüssel und folge der [Update-Anleitung](update.md).

## Aus dem Quellcode

```sh
git clone https://github.com/CyberspaceConsulting/ClinicPulse.git
cd ClinicPulse
sh deploy/install.sh ./clinicpulse
```

## Nächste Schritte

- [Docker Compose](docker-compose.md): Dienste, Netzwerke und Speicher
- [Umgebungsvariablen und Secrets](environment-variables.md): Konfiguration und Schlüsselverwaltung
- [Fehlerbehebung](../troubleshooting.md): Status und Logs prüfen
