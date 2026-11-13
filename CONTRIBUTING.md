# Zu Medora beitragen

Danke für dein Interesse an Medora! Dieses Dokument beschreibt, wie du das Projekt lokal einrichtest, welche Regeln für Beiträge gelten und wie Änderungen eingereicht werden.

Medora befindet sich in einer frühen Alpha-Phase. Für das Repository ist derzeit keine Lizenzdatei hinterlegt (siehe [README.md](README.md)).

## Inhalt

1. [Verhaltenskodex](#verhaltenskodex)
2. [Möglichkeiten beizutragen](#möglichkeiten-beizutragen)
3. [Projektübersicht](#projektübersicht)
4. [Voraussetzungen](#voraussetzungen)
5. [Lokales Setup](#lokales-setup)
6. [Anwendung starten](#anwendung-starten)
7. [Coding-Regeln](#coding-regeln)
8. [Tests](#tests)
9. [Commits](#commits)
10. [Pull Requests](#pull-requests)
11. [Branches und Releases](#branches-und-releases)
12. [Fehler melden und Features vorschlagen](#fehler-melden-und-features-vorschlagen)
13. [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)

## Verhaltenskodex

Sei respektvoll, konstruktiv und geduldig. Reviews beziehen sich auf den Code, nicht auf die Person. Belästigung, persönliche Angriffe und diskriminierende Sprache sind in Issues, Pull Requests, Diskussionen und Commit-Nachrichten nicht erlaubt.

## Möglichkeiten beizutragen

- Fehler aus den [Issues](https://github.com/CyberspaceConsulting/Medora/issues) beheben.
- Funktionen umsetzen, die in einem Issue besprochen und akzeptiert wurden.
- Dokumentation verbessern (`README.md`, `TEST.md`, diese Datei).
- Tests ergänzen, besonders für Berechtigungen, Validierung und Arbeitszeitprüfungen.
- Offene Pull Requests prüfen.

Bei größeren Änderungen bitte **zuerst ein Issue eröffnen**, um den Umfang abzustimmen, bevor du Code schreibst.

## Projektübersicht

Medora ist eine selbst gehostete Webanwendung für die Dienstplanung in Teams mit Schichtbetrieb. Das Backend ist eine Python-API, das Frontend eine Vue-3-Anwendung mit Vite und TypeScript. Betrieben wird alles über Docker Compose.

```
backend/
  app/            # API, Datenmodelle, Sicherheit, Planung, Backup, Lizenzprüfung
  requirements.txt # aus uv.lock erzeugt
pyproject.toml    # Python-Abhängigkeiten
uv.lock           # aufgelöste Python-Abhängigkeiten
Makefile          # Export nach backend/requirements.txt
frontend/
  src/            # Vue 3 + TypeScript
  nginx.conf
tests/
  backend/        # pytest
  frontend/       # Playwright (Browser-Tests)
  run-tests.sh    # richtet eine venv ein und startet die Backend-Tests
docker/           # Dockerfiles und Compose-Dateien
deploy/           # Installations- und Hilfsskripte
```

## Voraussetzungen

| Werkzeug                  | Zweck                                          |
| ------------------------- | ---------------------------------------------- |
| Python 3.12               | Backend und Backend-Tests                      |
| Node.js 22 und npm        | Frontend-Build und Browser-Tests               |
| Docker Engine, Compose v2 | Anwendung starten                              |
| OpenSSL                   | Verschlüsselungsschlüssel erzeugen             |
| `git`                     | Versionsverwaltung                             |
| `uv` 0.13.x und `make`    | Python-Abhängigkeiten aktualisieren            |

## Lokales Setup

```bash
# 1. Repository auf GitHub forken und den Fork klonen
git clone https://github.com/<dein-benutzername>/Medora.git
cd Medora

# 2. Upstream hinzufügen, um den Fork aktuell zu halten
git remote add upstream https://github.com/CyberspaceConsulting/Medora.git

# 3. Frontend-Abhängigkeiten installieren
npm --prefix frontend ci
```

Die Backend-Abhängigkeiten installiert `./tests/run-tests.sh` bei Bedarf in `backend/.venv`.

## Anwendung starten

Die Schritte für Schlüssel und Secrets stehen im [Schnellstart der README](README.md#schnellstart-aus-dem-quellcode). Danach:

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

Für die Frontend-Entwicklung:

```bash
cd frontend
npm run dev
```

## Coding-Regeln

- **API-Verträge nicht brechen.** Das Frontend hängt von bestehenden Endpunktpfaden und Antwortformaten ab. Neue Endpunkte oder Felder hinzufügen, statt bestehende umzubenennen oder zu entfernen.
- **Berechtigungen prüfen.** Jede neue oder geänderte Funktion, die Daten liefert oder ändert, muss serverseitig auf Rolle und Zugehörigkeit geprüft werden.
- **Keine Geheimnisse im Repository.** Keine Zugangsdaten, Lizenz-Tokens, Schlüssel oder `secrets/`-Dateien committen.
- **Keine echten Personen- oder Gesundheitsdaten** in Code, Testdaten, Logs, Screenshots oder Beschreibungen.
- **Datenschutz-Check muss grün sein.** Neue Textspalten mit möglichem Personenbezug werden verschlüsselt gespeichert (`EncryptedText`) oder im Test begründet eingeordnet; neue Browser-Speicherschlüssel müssen bewusst freigegeben werden. Siehe [docs/development/privacy-checks.md](docs/development/privacy-checks.md).
- **Abhängigkeiten sparsam hinzufügen** und begründen. Python-Abhängigkeiten ausschließlich in `pyproject.toml` ändern, danach im Repository-Hauptverzeichnis `uv lock && make export` ausführen und `pyproject.toml`, `uv.lock` und `backend/requirements.txt` gemeinsam committen. `backend/requirements.txt` nicht von Hand bearbeiten. Frontend-Änderungen an Abhängigkeiten immer mit `package-lock.json` committen.
- Dependabot aktualisiert Python-Abhängigkeiten im uv-Projekt. Falls der erzeugte Requirements-Export in einem Dependabot-PR fehlt, `make export` ausführen und das Ergebnis zum PR hinzufügen.
- **Das Frontend muss bauen:** `npm run build` führt auch die TypeScript-Prüfung (`vue-tsc`) aus.
- Hinweise zur laufenden Lokalisierung und zu Übersetzungskatalogen stehen in [docs/development/localization.md](docs/development/localization.md).
- Funktionen klein halten und keine spekulativen Abstraktionen einführen.

## Tests

Änderungen müssen durch passende Tests abgesichert sein. Details stehen in [TEST.md](TEST.md).

```bash
# Backend (alle Tests; Datenschutz einzeln: ./tests/run-tests.sh -m privacy)
./tests/run-tests.sh

# Frontend
cd frontend
npm ci
npm run build
npx playwright install --with-deps chromium firefox
npm run test:e2e              # beide Browser
# oder getrennt: npm run test:e2e:chromium / npm run test:e2e:firefox
```

- **Tests laufen offline** und verwenden weder Produktivdaten noch externe Dienste.
- API- und Berechtigungsänderungen brauchen Tests für Erfolgsfälle, Validierung und fehlende Berechtigungen.
- PostgreSQL-Integrationstests laufen nur mit `TEST_POSTGRES_URL` und ausschließlich gegen eine entbehrliche Testdatenbank.
- Lässt sich ein Codepfad nicht testen, erkläre das in der PR-Beschreibung und beschreibe die manuelle Prüfung.

## Commits

- Ein logisches Thema pro Commit. Rauschende Commits ("wip", "typo") vor dem PR zusammenführen.
- Commit-Nachrichten im Imperativ: "Add shift validation", nicht "Added".
- Betreffzeile höchstens 72 Zeichen; einen Text ergänzen, wenn das *Warum* nicht offensichtlich ist.
- Issues mit `Closes #123` verknüpfen.
- Hooks nicht mit `--no-verify` umgehen.
- Niemals auf `main` force-pushen. Auf dem eigenen PR-Branch ist Force-Push nach einem Rebase in Ordnung.

## Pull Requests

Vor dem Öffnen:

1. Auf den aktuellen `upstream/main` rebasen.
2. Backend-Tests laufen durch: `./tests/run-tests.sh`.
3. Bei Frontend-Änderungen laufen `npm run build` und `npm run test:e2e` durch.
4. Neues Verhalten ist durch Tests abgedeckt oder die Beschreibung erklärt, warum nicht.
5. Bei nutzersichtbaren Änderungen sind README oder Dokumentation im selben PR aktualisiert.
6. Die Version wird nicht angehoben; das übernehmen die Maintainer.

Die PR-Beschreibung enthält:

- **Was** sich ändert und **warum**.
- Das verknüpfte Issue, falls vorhanden.
- Screenshots bei UI-Änderungen (ohne echte Daten).
- Einen Testplan: was du ausgeführt und manuell geprüft hast.
- Bewusst ausgelassene Folgearbeiten.

Reviews sind ein Austausch. Rechne mit ein bis zwei Feedbackrunden.

## Branches und Releases

- Änderungen laufen per Pull Request in den Hauptbranch des Repositorys. Eine Vorgabe für die Zielbranch klären die Maintainer im Issue.
- Releases und Versionsnummern verwalten die Maintainer. Installationsartefakte stehen unter [GitHub Releases](https://github.com/CyberspaceConsulting/Medora/releases).

## Fehler melden und Features vorschlagen

- Nutze die [Issues](https://github.com/CyberspaceConsulting/Medora/issues).
- Bei Fehlern: Medora-Version bzw. Commit, Betriebsart (Docker Compose oder lokal), Schritte zur Reproduktion, erwartetes und tatsächliches Verhalten sowie bereinigte Logs (`docker compose logs --tail 100`).
- Bei Feature-Wünschen: zuerst das Problem beschreiben, dann die Lösungsidee.

## Sicherheit und Datenschutz

**Eröffne kein öffentliches Issue für Sicherheitslücken.** Schreibe stattdessen eine E-Mail an **info@cyberspaceconsulting.de** mit Beschreibung und Reproduktion.

Medora ist ein Entwicklungsprojekt und nicht für den produktiven Einsatz in Kliniken freigegeben. Bitte keine Zugangsdaten, Lizenz-Tokens, Schlüssel oder echten Personen- und Gesundheitsdaten in Issues, Pull Requests oder Testdaten veröffentlichen.

Danke für deinen Beitrag! 🩺
