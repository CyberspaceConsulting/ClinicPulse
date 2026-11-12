# Sicherheit

## Anmeldung und Sitzungen

- Passwörter werden mit scrypt gehasht.
- Sitzungen laufen nach Inaktivität ab. Die Dauer stellt der Administrator ein (1–120 Minuten); danach folgt „Session expired due to inactivity“.
- **Anmeldedrosselung:** Nach zu vielen Fehlversuchen für dieselbe Kombination aus IP-Adresse und Benutzername antwortet die API mit HTTP 429 und dem Header `Retry-After`. Das Zeitfenster beträgt 15 Minuten. Die Schlüssel werden nur als HMAC gespeichert.

## Passwortprüfung

Neue Passwörter können gegen „Have I Been Pwned“ geprüft werden. Dabei wird nur ein Hash-Präfix übertragen (k-Anonymität), nie das Passwort. Ist der Dienst nicht erreichbar, meldet die API HTTP 503 bzw. 502.

## Verschlüsselung

Sensible Datenbankfelder werden mit einem Schlüssel aus dem Docker-Volume `clinicpulse_keys` verschlüsselt. Das Volume ist selbst nicht automatisch verschlüsselt und für Docker-Administratoren zugänglich. Anwendungsbackups und separate Schlüssel-Backups sind verschlüsselt, siehe [Backup](backup.md). Die Datenbank liegt in einem internen Docker-Netzwerk.

## Datenschutz im Betrieb

- API-Antworten werden mit `Cache-Control: no-store` ausgeliefert und landen nicht in Browser- oder Proxy-Caches.
- Personenbezogene Felder (Namen, E-Mail, Telefon, Adresse, Geburtsdatum, Abwesenheitsnotizen) liegen nur verschlüsselt in der Datenbank; Logs und Audit-Protokoll enthalten keine Passwörter oder Personendaten.
- Beschäftigte sehen nur eigene Daten. Bei Personen in mehreren Abteilungen sehen andere Abteilungen weder fremde Qualifikationen noch Notizen oder Entscheidungsdaten von Abwesenheiten.
- Der Browser speichert nur nicht personenbezogene Einstellungen (Sprache, Darstellung, Hinweisstatus).
- Bekannte Ausnahme: Benutzername und Notiz eines Archiv-Eintrags (`plan_archives.created_by`, `plan_archives.note`) liegen noch im Klartext.

Diese Zusagen prüft der Pflicht-Check „Datenschutz“ bei jeder Änderung automatisch, siehe [Datenschutz-Prüfungen](../development/privacy-checks.md). Er ersetzt keine unabhängige Datenschutzprüfung.

## Berechtigungen

Alle Endpunkte prüfen serverseitig Rolle, Abteilung und Recht (Ansehen, Bearbeiten, Freigeben, Verwalten). Siehe [Rollen und Berechtigungen](roles-and-permissions.md).

## Sicherheitslücken melden

Bitte nicht öffentlich, sondern per E-Mail an info@cyberspaceconsulting.de.
