# Datenschutz-Prüfungen

Der GitHub-Workflow `Datenschutz` (`.github/workflows/privacy.yml`) führt bei jedem Pull Request und bei Pushes auf `main` und `alpha` die Tests mit der Markierung `privacy` aus. Lokal:

```bash
./tests/run-tests.sh -m privacy
```

Die Tests liegen in `tests/backend/test_privacy.py`. Sie sichern ab, dass:

- **Personenbezogene Spalten verschlüsselt sind.** Jede neue Textspalte, deren Name auf Personenbezug oder Geheimnisse hindeutet (z. B. `name`, `email`, `note`, `token`), muss mit `EncryptedText` gespeichert oder in der Liste `ACCEPTED_PLAINTEXT` mit Begründung eingeordnet werden.
- **Daten nie im Klartext in der Datenbank liegen.** Testdaten (Name, E-Mail, Telefon, Adresse, Geburtsdatum, Abwesenheitsnotiz, Passwort) werden angelegt und der rohe Datenbankinhalt wird durchsucht.
- **Logs und Audit-Protokoll keine Personendaten oder Passwörter enthalten.**
- **API-Antworten keine Geheimnisse enthalten** (Passwort-Hashes, Signaturschlüssel, SMTP-Passwort, Lizenztoken) und nicht gecacht werden (`Cache-Control: no-store`).
- **Sichtbarkeitsregeln gelten:** Administratoren sehen keine Dienstpläne und Abwesenheiten, Mitarbeitende nur eigene Daten, andere Abteilungen keine Personen- oder Notizdaten.
- **Das Repository keine Geheimnisse oder Datendateien enthält** und der Browser-Speicher nur nicht personenbezogene Einstellungen ablegt. Ein neuer Browser-Speicherschlüssel muss bewusst in der Testliste ergänzt werden.

Die Tests ersetzen keine unabhängige Datenschutzprüfung und keine Datenschutz-Folgenabschätzung.

## Bekannte Lücken

`KNOWN_PLAINTEXT_GAPS` in `test_privacy.py` listet Klartextspalten, die noch verschlüsselt werden sollten (derzeit `plan_archives.created_by` und `plan_archives.note`). Wird eine Lücke geschlossen, schlägt der Test an, bis der Eintrag entfernt ist.

## Als Pflicht-Check einrichten

Der Prüfname ist `Datenschutz`. In den Repository-Einstellungen unter **Settings → Branches** (oder **Rules → Rulesets**) für `alpha` und `main` die Regel „Require status checks to pass before merging“ aktivieren und `Datenschutz` auswählen. Der Check erscheint dort erst, nachdem der Workflow einmal gelaufen ist. Per CLI, mit Administratorrechten:

```bash
gh api -X PUT repos/CyberspaceConsulting/ClinicPulse/branches/alpha/protection \
  -H "Accept: application/vnd.github+json" \
  -F required_status_checks[strict]=false \
  -f required_status_checks[contexts][]=Datenschutz \
  -F enforce_admins=false \
  -F required_pull_request_reviews=null \
  -F restrictions=null
```

Der Befehl ersetzt die bestehenden Schutzregeln des Branches. Zurzeit ist `alpha` ungeschützt; vorhandene Regeln vorher mit `gh api repos/CyberspaceConsulting/ClinicPulse/branches/alpha/protection` prüfen.
