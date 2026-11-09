[![Tests](https://github.com/the1andoni/ClinicPulse/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/the1andoni/ClinicPulse/actions/workflows/tests.yml) [![Dependency Graph](https://github.com/the1andoni/ClinicPulse/actions/workflows/dependabot/update-graph/badge.svg?branch=main)](https://github.com/the1andoni/ClinicPulse/actions/workflows/dependabot/update-graph) [![Release images](https://github.com/the1andoni/ClinicPulse/actions/workflows/release-images.yml/badge.svg?branch=main)](https://github.com/the1andoni/ClinicPulse/actions/workflows/release-images.yml)

# ClinicPulse

ClinicPulse ist eine selbst gehostete Webanwendung für die Dienstplanung in Teams
mit Schichtbetrieb. Das Projekt befindet sich in einer frühen Alpha-Phase und
wird aktiv weiterentwickelt.

ClinicPulse bietet unter anderem:

- Wochen- und Tagesübersichten mit offenen Schichtpositionen
- Verwaltung von Teams, Abteilungen, Mitarbeitenden und Benutzerrollen
- Dienstzuweisungen, Abwesenheitsanträge und Freigabeabläufe
- Vorschläge zur Schichtbesetzung und regelbasierte Planungsentwürfe
- grundlegende Prüfungen geplanter Arbeits- und Ruhezeiten
- lokale Datensicherung und Wiederherstellung

## Status und Eignung

ClinicPulse ist ein Entwicklungsprojekt und keine produktionsreife Lösung für
den Einsatz in Kliniken. Es ersetzt weder eine vollständige Arbeitszeiterfassung
noch eine Prüfung durch qualifizierte Fachleute. Die implementierten Planungs-
und Arbeitszeitprüfungen decken nicht alle gesetzlichen, tariflichen oder
betrieblichen Anforderungen ab und sind keine Rechtskonformitätsgarantie.

Vor einem produktiven Einsatz sind eine unabhängige Sicherheits- und
Datenschutzprüfung, ein erprobtes Betriebs- und Wiederherstellungskonzept sowie
die Prüfung der jeweils geltenden Anforderungen erforderlich. Bis dahin sollten
keine echten Gesundheits-, Beschäftigten- oder sonstigen sensiblen Daten
verarbeitet werden.

## Schnellstart aus dem Quellcode

Voraussetzungen: Docker Engine, Docker Compose v2 und OpenSSL.

```sh
git clone https://github.com/the1andoni/ClinicPulse.git
cd ClinicPulse

mkdir -p secrets
chmod 700 secrets
umask 077
if [ ! -f secrets/data_encryption_key ]; then
  openssl rand -base64 48 > secrets/data_encryption_key
fi
touch secrets/smtp_password
chmod 600 secrets/data_encryption_key secrets/smtp_password

docker compose -f docker/docker-compose.yml up --build -d
```

Rufe anschließend <http://localhost:8080> auf. Für die Ersteinrichtung ist ein
gültiger Lizenzzugang erforderlich. Der API-Dienst benötigt ausgehenden HTTPS-
Zugriff auf den konfigurierten Lizenzdienst; dessen Adresse kann mit
`CLINICPULSE_LICENSE_API_URL` festgelegt werden.

Nützliche Befehle:

```sh
docker compose -f docker/docker-compose.yml logs -f
docker compose -f docker/docker-compose.yml down
```

Die Datenbank wird in einem Docker-Volume gespeichert. Sichere
`secrets/data_encryption_key` getrennt und geschützt: Ohne diesen Schlüssel
können verschlüsselte Daten nicht mehr gelesen werden. SMTP ist optional; für
Einladungs-E-Mails müssen SMTP und die öffentliche HTTPS-Adresse der Instanz
konfiguriert werden. Details zu verfügbaren Installationsartefakten findest du
unter [GitHub Releases](https://github.com/the1andoni/ClinicPulse/releases).

## Entwicklung und Tests

Backend-Tests:

```sh
./tests/run-tests.sh
```

Frontend-Build:

```sh
cd frontend
npm ci
npm run build
```

Weitere Hinweise zu Testarten und lokalen Voraussetzungen stehen in
[TEST.md](TEST.md).

## GitHub-Automatisierung

Der Labeler versieht Pull Requests anhand der Pfade in
`.github/labeler.yml` mit Labels. Der Workflow „Add to project“ fügt neue
Issues und Pull Requests dem Projekt
[ClinicPulse](https://github.com/users/the1andoni/projects/8) hinzu. Dafür
muss im Repository unter **Settings → Secrets and variables → Actions** das
Secret `ADD_TO_PROJECT_PAT` eingerichtet sein: ein persönliches Zugriffstoken
mit Zugriff auf das Projekt (bei klassischen Tokens die Scopes `project` und
`repo`). Ohne dieses Secret schlägt der Workflow fehl.

## Sicherheit

Bitte keine Zugangsdaten, Lizenz-Tokens, Schlüssel oder echten Personen- und
Gesundheitsdaten in Issues, Pull Requests oder Testdaten veröffentlichen.

## Lizenz

Für dieses Repository ist derzeit keine Lizenzdatei hinterlegt. Die
Veröffentlichung auf GitHub gewährt daher nicht automatisch Rechte zur Nutzung,
Änderung oder Weiterverbreitung des Quellcodes.
