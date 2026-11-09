# Tests

Änderungen sollten durch passende Tests abgesichert werden. API- und
Berechtigungsänderungen benötigen insbesondere Tests für Erfolgsfälle,
Validierung und fehlende Berechtigungen. Tests dürfen keine Produktivdaten oder
externen Dienste verwenden.

## Backend

Das Skript richtet bei Bedarf eine virtuelle Umgebung ein und führt die
Backend-Tests aus:

```sh
./run-tests.sh
```

Alternativ:

```sh
cd backend
python -m pytest -q
```

PostgreSQL-Integrationstests werden übersprungen, wenn keine separate
Testdatenbank über `TEST_POSTGRES_URL` konfiguriert ist. Verwende dafür
ausschließlich eine entbehrliche lokale Testdatenbank, niemals eine
Produktivdatenbank.

## Frontend

Build und Browser-Tests:

```sh
cd frontend
npm ci
npm run build
npx playwright install --with-deps chromium
npm run test:e2e
```

Die Browser-Tests verwenden simulierte API-Antworten und ersetzen keine
Integrationstests mit einem laufenden Backend.
