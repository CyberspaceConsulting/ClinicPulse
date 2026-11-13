# Installation

Medora wird als Release mit Docker Compose gestartet. Weboberfläche, API und PostgreSQL laufen dabei in getrennten Containern.

## Voraussetzungen

- Docker Engine mit Docker Compose v2
- `curl`, `openssl`, `sha256sum` und [Cosign](https://docs.sigstore.dev/cosign/system_config/installation/)
- Ein gültiger Lizenzzugang und ausgehender HTTPS-Zugriff des Backends auf den Lizenzdienst

## Release installieren

Wähle ein Release auf [GitHub Releases](https://github.com/CyberspaceConsulting/Medora/releases) und ersetze den Tag im Beispiel. Das Skript prüft die Sigstore-Signatur der Release-Prüfsummen und die Prüfsummen von Installer und Compose-Datei. Die Compose-Datei pinnt Backend und Web per Image-Digest. Alpha-Releases werden von GitHubs `releases/latest` nicht erfasst.

Bei einem Update mit bestehender Datenbank kann `v-0.3.4.1-alpha` beim Start scheitern; siehe [Fehlerbehebung](../troubleshooting.md#fehlende-fahrzeugspalte-beim-start).

```sh
(
  set -eu
  target="$(pwd)/medora"
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  url=https://github.com/CyberspaceConsulting/Medora/releases/download/v-0.3.4.1-alpha
  curl -fsSL -o "$tmpdir/install.sh" "$url/install.sh"
  curl -fsSL -o "$tmpdir/compose.yaml" "$url/compose.yaml"
  curl -fsSL -o "$tmpdir/SHA256SUMS" "$url/SHA256SUMS"
  curl -fsSL -o "$tmpdir/SHA256SUMS.sigstore.json" "$url/SHA256SUMS.sigstore.json"
  curl -fsSL -o "$tmpdir/verify-integrity.sh" "$url/verify-integrity.sh"
  cd "$tmpdir"
  cosign verify-blob \
    --bundle SHA256SUMS.sigstore.json \
    --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/Medora/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    SHA256SUMS
  awk '$2 == "install.sh" || $2 == "compose.yaml" || $2 == "verify-integrity.sh" { print; count++ } END { if (count != 3) exit 1 }' SHA256SUMS > install.sha256
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
| Docker-Volume `medora_data` | PostgreSQL-Datenbank |
| Docker-Volume `medora_keys` | Automatisch verwalteter Schlüssel und optionales SMTP-Passwort |
| `medora/backups` | Verschlüsselte Anwendungssicherungen |

Die Volume-Verwaltung gilt für den aktuellen Quellcode und künftige Releases mit dieser Funktion. Das Beispielrelease `v-0.3.4.1-alpha` verwendet weiterhin Dateien unter `medora/secrets`. Beide Volumes bleiben beim Neustart und Update erhalten und dürfen nicht gelöscht werden, solange Daten benötigt werden.

## Anderer Port

Setze vor der Installation `MEDORA_PORT`, zum Beispiel `export MEDORA_PORT=9090`. Damit spätere Compose-Aufrufe denselben Port verwenden, trage `MEDORA_PORT=9090` in `medora/.env` ein. Die Anwendung ist dann unter `http://localhost:9090` erreichbar.

## Updates

Release-Images sind versionsgebunden. Ein `docker compose pull` allein wechselt nicht auf eine neue Version. Sichere Daten und Schlüssel und folge der [Update-Anleitung](update.md).

## Manuelle Integritätsprüfung

Der Installer prüft die signierte Release-Prüfsummenliste automatisch. Für die unabhängige Notfallprüfung nicht dem installierten Prüfer vertrauen, sondern Prüfer und Signaturdateien frisch aus demselben GitHub-Release laden. Das folgende Beispiel im Installationsverzeichnis ausführen und `v-0.3.4.1-alpha` durch den installierten Release-Tag ersetzen:

```sh
(
  set -eu
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  url=https://github.com/CyberspaceConsulting/Medora/releases/download/v-0.3.4.1-alpha
  for asset in compose.yaml SHA256SUMS SHA256SUMS.sigstore.json verify-integrity.sh; do
    curl -fsSL -o "$tmpdir/$asset" "$url/$asset"
  done
  (
    cd "$tmpdir"
    cosign verify-blob \
      --bundle SHA256SUMS.sigstore.json \
      --certificate-identity-regexp '^https://github\.com/CyberspaceConsulting/Medora/.github/workflows/release-images\.yml@refs/tags/v[^/]+$' \
      --certificate-oidc-issuer https://token.actions.githubusercontent.com \
      SHA256SUMS
    awk '$2 == "compose.yaml" || $2 == "verify-integrity.sh" { print; count++ } END { if (count != 2) exit 1 }' SHA256SUMS > assets.sha256
    sha256sum --check assets.sha256
  )
  sh "$tmpdir/verify-integrity.sh" --release-dir "$tmpdir" --project-dir "$PWD"
)
```

Die manuelle Prüfung läuft außerhalb der Anwendung. Cosign prüft die Signatur gegen die festgelegte GitHub-Actions-Identität; der frisch geladene Prüfer vergleicht danach die laufenden Backend- und Web-Container mit den signierten Image-Digests. Benötigt werden Cosign, Docker Compose, `curl` und `sha256sum`.

## Aus dem Quellcode

```sh
git clone https://github.com/CyberspaceConsulting/Medora.git
cd Medora
sh deploy/install.sh ./medora
```

## Nächste Schritte

- [Docker Compose](docker-compose.md): Dienste, Netzwerke und Speicher
- [Umgebungsvariablen und Secrets](environment-variables.md): Konfiguration und Schlüsselverwaltung
- [Fehlerbehebung](../troubleshooting.md): Status und Logs prüfen
