[![Tests](https://github.com/CyberspaceConsulting/Medora/actions/workflows/tests.yml/badge.svg?branch=alpha)](https://github.com/CyberspaceConsulting/Medora/actions/workflows/tests.yml) [![Dependency Graph](https://github.com/CyberspaceConsulting/Medora/actions/workflows/dependabot/update-graph/badge.svg?branch=alpha)](https://github.com/CyberspaceConsulting/Medora/actions/workflows/dependabot/update-graph) [![Build and Push Docker Image](https://github.com/CyberspaceConsulting/Medora/actions/workflows/release-images.yml/badge.svg)](https://github.com/CyberspaceConsulting/Medora/actions/workflows/release-images.yml)

# Medora

Medora ist eine selbst gehostete Webanwendung für die Dienstplanung in Teams
mit Schichtbetrieb. Das Projekt befindet sich in einer frühen Alpha-Phase und
wird aktiv weiterentwickelt.

Medora bietet unter anderem:

- Wochen- und Tagesübersichten mit offenen Schichtpositionen
- Verwaltung von Teams, Abteilungen, Mitarbeitenden und Benutzerrollen
- Dienstzuweisungen, Abwesenheitsanträge und Freigabeabläufe
- Vorschläge zur Schichtbesetzung und regelbasierte Planungsentwürfe
- grundlegende Prüfungen geplanter Arbeits- und Ruhezeiten
- lokale Datensicherung und Wiederherstellung

## Status und Eignung

Medora ist ein Entwicklungsprojekt und keine produktionsreife Lösung für
den Einsatz in Kliniken. Es ersetzt weder eine vollständige Arbeitszeiterfassung
noch eine Prüfung durch qualifizierte Fachleute. Die implementierten Planungs-
und Arbeitszeitprüfungen decken nicht alle gesetzlichen, tariflichen oder
betrieblichen Anforderungen ab und sind keine Rechtskonformitätsgarantie.

Vor einem produktiven Einsatz sind eine unabhängige Sicherheits- und
Datenschutzprüfung, ein erprobtes Betriebs- und Wiederherstellungskonzept sowie
die Prüfung der jeweils geltenden Anforderungen erforderlich. Bis dahin sollten
keine echten Gesundheits-, Beschäftigten- oder sonstigen sensiblen Daten
verarbeitet werden.

## Installation eines Releases

Voraussetzungen: Docker Engine mit Compose v2, `curl`, `openssl` und
`sha256sum`. Da bisher nur Alpha-Vorabversionen veröffentlicht wurden,
verweist `releases/latest` nicht auf ein verfügbares stabiles Release. Die
folgenden Befehle installieren daher ausdrücklich `v-0.2.0-alpha`. Sie laden
Installer und Compose-Datei aus demselben Release und prüfen deren Prüfsummen.
Die Installation wird im Verzeichnis `./medora` angelegt.

```sh
(
  set -eu
  target="$(pwd)/medora"
  tmpdir=$(mktemp -d)
  trap 'rm -rf "$tmpdir"' EXIT
  url=https://github.com/CyberspaceConsulting/Medora/releases/download/v-0.2.0-alpha
  curl -fsSL -o "$tmpdir/install.sh" "$url/install.sh"
  curl -fsSL -o "$tmpdir/compose.yaml" "$url/compose.yaml"
  curl -fsSL -o "$tmpdir/SHA256SUMS" "$url/SHA256SUMS"
  cd "$tmpdir"
  awk '$2 == "install.sh" { install++; print } $2 == "compose.yaml" { compose++; print } END { if (install != 1 || compose != 1) exit 1 }' SHA256SUMS > install.sha256
  sha256sum --check install.sha256
  sh ./install.sh "$target"
)
```

Danach ist Medora unter <http://localhost:8080> erreichbar. Für Updates
siehe die [Docker-Update-Anleitung](docs/getting-started/update.md). Ein
`docker compose pull` allein aktualisiert nicht die festgelegte Release-Version.
Neuere Versionen findest du unter [GitHub Releases](https://github.com/CyberspaceConsulting/Medora/releases).

Den Schlüssel unter `medora/secrets/data_encryption_key` separat sichern.
Ohne ihn können verschlüsselte Daten nicht wiederhergestellt werden.
Dieses Beispielrelease verwendet noch die dateibasierte Schlüsselverwaltung.
Der aktuelle Quellcode verwaltet Schlüssel dagegen in einem eigenen Docker-Volume;
siehe [Backup und Wiederherstellung](docs/features/backup.md).

## Schnellstart aus dem Quellcode

Voraussetzungen: Docker Engine und Docker Compose v2.

```sh
git clone https://github.com/CyberspaceConsulting/Medora.git
cd Medora

sh deploy/install.sh "$PWD"
```

Rufe anschließend <http://localhost:8080> auf. Für die Ersteinrichtung ist ein
gültiger Lizenzzugang erforderlich. Der API-Dienst benötigt ausgehenden HTTPS-
Zugriff auf den konfigurierten Lizenzdienst; dessen Adresse kann mit
`MEDORA_LICENSE_API_URL` festgelegt werden.

Nützliche Befehle:

```sh
docker compose -f docker/docker-compose.yml logs -f
docker compose -f docker/docker-compose.yml down
```

Die Datenbank und der automatisch erzeugte Datenschlüssel werden in getrennten
Docker-Volumes gespeichert. Sichere den Schlüssel verschlüsselt und getrennt
von der Datenbank: Ohne ihn können verschlüsselte Daten nicht mehr gelesen
werden. SMTP ist optional; für
Einladungs-E-Mails müssen SMTP und die öffentliche HTTPS-Adresse der Instanz
konfiguriert werden. Details zu verfügbaren Installationsartefakten findest du
unter [GitHub Releases](https://github.com/CyberspaceConsulting/Medora/releases).

## Entwicklung und Tests

Backend-Tests:

```sh
./run-tests.sh
```

Frontend-Build:

```sh
cd frontend
npm ci
npm run build
```

Weitere Hinweise zu Testarten und lokalen Voraussetzungen stehen in
[TEST.md](TEST.md). Beiträge sind in [CONTRIBUTING.md](CONTRIBUTING.md)
beschrieben, die ausführliche Dokumentation steht in [docs/](docs/index.md).

## Sicherheit

Bitte keine Zugangsdaten, Lizenz-Tokens, Schlüssel oder echten Personen- und
Gesundheitsdaten in Issues, Pull Requests oder Testdaten veröffentlichen.

## Lizenz

Für dieses Repository ist derzeit keine Lizenzdatei hinterlegt. Die
Veröffentlichung auf GitHub gewährt daher nicht automatisch Rechte zur Nutzung,
Änderung oder Weiterverbreitung des Quellcodes.
