# Sicherheit

## Anmeldung und Sitzungen

- Passwörter werden mit scrypt gehasht.
- Sitzungen laufen nach Inaktivität ab. Die Dauer stellt der Administrator ein (1–120 Minuten); danach folgt „Session expired due to inactivity“.
- **Anmeldedrosselung:** Nach zu vielen Fehlversuchen für dieselbe Kombination aus IP-Adresse und Benutzername antwortet die API mit HTTP 429 und dem Header `Retry-After`. Das Zeitfenster beträgt 15 Minuten. Die Schlüssel werden nur als HMAC gespeichert.

## Passwortprüfung

Neue Passwörter können gegen „Have I Been Pwned“ geprüft werden. Dabei wird nur ein Hash-Präfix übertragen (k-Anonymität), nie das Passwort. Ist der Dienst nicht erreichbar, meldet die API HTTP 503 bzw. 502.

## Verschlüsselung

Sensible Daten werden mit dem Schlüssel aus `secrets/data_encryption_key` verschlüsselt. Backups sind zusätzlich nur mit einem Wiederherstellungsschlüssel lesbar, siehe [Backup](backup.md). Die Datenbank liegt in einem internen Docker-Netzwerk.

## Berechtigungen

Alle Endpunkte prüfen serverseitig Rolle, Abteilung und Recht (Ansehen, Bearbeiten, Freigeben, Verwalten). Siehe [Rollen und Berechtigungen](roles-and-permissions.md).

## Sicherheitslücken melden

Bitte nicht öffentlich, sondern per E-Mail an info@cyberspaceconsulting.de.
