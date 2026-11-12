# Tests

Änderungen sollten durch passende Tests abgesichert werden. API- und
Berechtigungsänderungen benötigen insbesondere Tests für Erfolgsfälle,
Validierung und fehlende Berechtigungen. Tests dürfen keine Produktivdaten oder
externen Dienste verwenden.

## Backend

Das Skript richtet bei Bedarf eine virtuelle Umgebung ein und führt die
Backend-Tests aus:

```sh
./tests/run-tests.sh
```

Alternativ:

```sh
cd backend
python -m pytest -q ../tests/backend
```

PostgreSQL-Integrationstests werden übersprungen, wenn keine separate
Testdatenbank über `TEST_POSTGRES_URL` konfiguriert ist. Verwende dafür
ausschließlich eine entbehrliche lokale Testdatenbank, niemals eine
Produktivdatenbank.

Der echte Docker-Compose-Smoke-Test baut und startet Web, Backend und PostgreSQL
und prüft API- sowie Web-Erreichbarkeit über den veröffentlichten Web-Port:

```sh
./tests/compose-smoke.sh
```

Er benötigt Docker Compose v2, `curl`, `openssl`, Python 3 und einen freien
lokalen TCP-Port. Der Test verwendet ein eigenes Compose-Projekt und räumt seine
Container, sein Volume und temporäre Schlüsseldateien anschließend wieder auf.

## Frontend

Build und Browser-Tests:

```sh
cd frontend
npm ci
npm run build
npx playwright install --with-deps chromium firefox
npm run test:e2e
```

Die Browser-Tests laufen mit Chromium und Firefox jeweils mit Desktop- und
schmalem Bildschirm. Firefox nutzt dabei auch für den schmalen Bildschirm
den Desktop-Browser, da Playwright keine mobile Firefox-Emulation unterstützt.
Einzelne Projekte lassen sich beispielsweise mit `npm run test:e2e -- --project=firefox`
ausführen. `PLAYWRIGHT_CHROMIUM_PATH` ersetzt nur die Chromium-Binärdatei;
Firefox verwendet den von Playwright installierten Browser.

Die Tests verwenden simulierte API-Antworten und ersetzen keine
Integrationstests mit einem laufenden Backend.

## GitHub Actions

Die Job-Zusammenfassungen zeigen den Status der einzelnen Schritte auch bei
Fehlern. Backend- und Browser-Jobs zählen erfolgreiche, fehlgeschlagene und
übersprungene Testfälle anhand ihrer JUnit-Berichte. Diese Berichte stehen als
Workflow-Artefakte bereit; bei fehlgeschlagenen Browsertests werden zusätzlich
die Playwright-Traces hochgeladen. Wird vor der Reporterstellung abgebrochen,
weist die Zusammenfassung auf den fehlenden Bericht und die Logs hin.
