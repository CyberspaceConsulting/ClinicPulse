# Fehlerbehebung

## Erste Schritte zur Diagnose

```sh
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs --tail 100 api
docker compose -f docker/docker-compose.yml logs --tail 100 db
```

Der Zustand der API lässt sich über `GET /api/health` prüfen. Bitte keine Zugangsdaten, Schlüssel oder echten Personendaten in Logs oder Issues veröffentlichen.

## Häufige Probleme

| Problem                                         | Ursache und Lösung                                                                                                       |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `docker compose` findet keine Datei             | Compose-Datei liegt unter `docker/docker-compose.yml`; Befehle mit `-f docker/docker-compose.yml` im Hauptverzeichnis ausführen. |
| `api` startet nicht / Secret fehlt              | `secrets/data_encryption_key` und `secrets/smtp_password` müssen existieren (siehe [Installation](getting-started/installation.md)). |
| `api` wartet auf `db`                           | Datenbank noch nicht gesund; `docker compose ... logs db` prüfen.                                                        |
| Verschlüsselte Daten nicht lesbar               | Der Schlüssel in `secrets/data_encryption_key` wurde geändert oder fehlt. Ursprünglichen Schlüssel wiederherstellen.      |
| Port 8080 belegt                                | `CLINICPULSE_PORT` auf einen freien Port setzen.                                                                         |
| Einrichtung scheitert an der Lizenz             | Ausgehenden HTTPS-Zugriff auf `CLINICPULSE_LICENSE_API_URL` prüfen (Firewall, Proxy, DNS).                               |
| Einladungs-E-Mails kommen nicht an              | [E-Mail](features/mail.md) prüfen: SMTP-Daten, TLS, öffentliche HTTPS-Adresse; Testversand nutzen.                       |
| Anmeldung wird mit „Zu viele Anmeldeversuche“ blockiert | 15-Minuten-Fenster abwarten (`Retry-After`-Header zeigt die Sekunden).                                           |
| Plötzlich abgemeldet                            | Sitzung wegen Inaktivität abgelaufen; Timeout unter Sicherheit einstellen.                                               |
| Änderungen sind nicht möglich                   | Lizenz im Nur-Lesen-Modus (HTTP 423); [Lizenz](features/license.md) erneuern.                                            |
| Planungsvorschau wird abgelehnt                 | Zeitraum oder Zahl offener Positionen zu groß; kürzer wählen (max. 63 Tage, 150 Positionen).                              |
| Schicht kann nicht zugewiesen werden            | Meldung lesen: Überschneidung, Abwesenheit, volle Besetzung oder [Arbeitszeitregel](features/work-rules.md).              |
| Backup lässt sich nicht einspielen              | Wiederherstellungsschlüssel und Passwort prüfen; Bestätigungstext `WIEDERHERSTELLEN` eingeben.                           |

## HTTP-Statuscodes

| Code | Bedeutung in ClinicPulse                                                    |
| ---- | --------------------------------------------------------------------------- |
| 400  | Ungültige Anfrage, z. B. ungültige oder abgelaufene Einladung               |
| 401  | Nicht angemeldet, Sitzung ungültig oder abgelaufen, falsche Zugangsdaten, Einrichtung fehlt |
| 403  | Fehlendes Recht oder Lizenz nicht aktiv/gesperrt                            |
| 404  | Objekt nicht gefunden                                                       |
| 409  | Konflikt: Duplikat, Objekt in Benutzung, Überschneidung, Arbeitszeitverstoß, Benutzerlimit |
| 413  | Backup-Datei zu groß                                                        |
| 422  | Eingabe ungültig (Validierung)                                              |
| 423  | Lizenz im Nur-Lesen-Modus                                                   |
| 429  | Zu viele Anmeldeversuche                                                    |
| 502  | Ungültige Antwort des Passwort-Prüfdienstes                                 |
| 503  | Externer Dienst nicht erreichbar (Lizenzserver, Passwortprüfung)            |

## Fehlermeldungen

Die API liefert Fehler als JSON mit dem Feld `detail`.

### Anmeldung und Sitzung

| Meldung                                  | Bedeutung / Lösung                                    |
| ---------------------------------------- | ----------------------------------------------------- |
| `Setup required`                         | Ersteinrichtung noch nicht abgeschlossen              |
| `Initial setup is already complete`      | Einrichtung wurde bereits durchgeführt                |
| `Invalid username or password`           | Zugangsdaten falsch                                   |
| `Current password is incorrect`          | Beim Passwortwechsel stimmt das aktuelle Passwort nicht |
| `Authentication required` / `Invalid or expired session` | Neu anmelden                          |
| `Session expired due to inactivity`      | Neu anmelden; Timeout anpassbar                       |
| `Zu viele Anmeldeversuche …` (429)       | Wartezeit abwarten                                    |
| `Invitation is invalid or expired`       | Einladung erneut senden lassen                        |

### Berechtigungen

| Meldung                                        | Bedeutung                                            |
| ---------------------------------------------- | ---------------------------------------------------- |
| `Administrator access required`                | nur für den Administrator                            |
| `Schedule view / editing / approval permission required` | Recht zum Ansehen, Bearbeiten bzw. Freigeben fehlt |
| `Team management access required`              | Verwaltungsrecht für das Team fehlt                  |
| `You can only plan / approve for your own department` | Nur eigene Abteilung                          |
| `Dienstpläne sind für den Administrator nicht einsehbar` | Administratoren sehen keine Dienstpläne    |
| `No department access is configured`           | Dem Konto ist keine Abteilung zugeordnet             |
| `Chief physicians are read-only`               | Chefärzte dürfen nicht schreiben                     |

### Konflikte bei der Planung

| Meldung                                              | Lösung                                         |
| ---------------------------------------------------- | ---------------------------------------------- |
| `Employee already has an overlapping shift`          | Andere Zeit oder Mitarbeitenden wählen         |
| `Employee is absent during this shift`               | Abwesenheit prüfen                             |
| `… is already fully staffed`                         | Schicht ist voll besetzt                       |
| `Employee and shift must belong to the same department` | Passende Abteilung wählen                   |
| `Work on Sundays or public holidays is disabled …`   | Sonntagsarbeit in der Betriebskonfiguration erlauben |
| `At least 15 Sundays per calendar year must remain free …` | Sonntagsdienste reduzieren               |
| `… legally required break (ArbZG §4)`                | Pause im Schichttyp ergänzen                   |
| `Date range must be 1–63 days` / `1–366 days`        | Zeitraum anpassen                              |

### Stammdaten

| Meldung                                                  | Lösung                                  |
| -------------------------------------------------------- | --------------------------------------- |
| `Department name already exists` / `Department already exists` | Anderen Namen wählen              |
| `Department is still in use`                             | Zuordnungen zuerst entfernen            |
| `Shift type name already exists` / `Shift type is in use` | Namen ändern bzw. Zuweisungen entfernen |
| `Employee has scheduled shifts` / `… in this period`     | Schichten zuerst entfernen              |
| `Employee has a linked login account`                    | Konto zuerst löschen                    |
| `Username is already in use`                             | Anderen Benutzernamen wählen            |
| `Role is not available for this facility type`           | Rolle passt nicht zur [Einrichtungsart](features/roles-and-permissions.md) |
| `Einrichtungsart fehlt` / `Bundesland fehlt`             | Betriebskonfiguration ergänzen          |
| `An absence already exists in this period`               | Überschneidende Abwesenheit prüfen      |
| `Absence was already decided`                            | Entscheidung kann nicht geändert werden |

### Lizenz

| Meldung                                           | Bedeutung / Lösung                                       |
| ------------------------------------------------- | -------------------------------------------------------- |
| `Diese Lizenz ist gesperrt` / `… nicht aktiv: <Grund>` | Lizenz beim Anbieter klären                         |
| `Lizenz enthält kein ClinicPulse-Kernfeature`     | Lizenz umfasst das Produkt nicht                         |
| `Licensed user limit reached`                     | Benutzerlimit erreicht                                   |
| `License is read-only: <Grund>` (423)             | Kulanzzeit abgelaufen; Lizenz erneuern                   |
| `Lizenzserver ist momentan nicht erreichbar` (503) | Netzwerk und `CLINICPULSE_LICENSE_API_URL` prüfen       |
| `Lizenzprüfung ist nicht verfügbar` (503)         | Später erneut versuchen                                  |
| `Lizenz-Token oder Status ungültig`               | Token prüfen bzw. neu abrufen                            |

### Backup

| Meldung                                                    | Lösung                                              |
| ---------------------------------------------------------- | --------------------------------------------------- |
| `Backup-Datei ist zu groß` (413)                           | Kleinere Datei oder anderen Weg zur Wiederherstellung nutzen |
| `Wiederherstellungsschlüssel fehlt oder ist ungültig`      | Richtige Schlüsseldatei und Passwort verwenden      |
| `Bitte „WIEDERHERSTELLEN“ zur Bestätigung eingeben`        | Bestätigungstext eingeben                           |
| `Für automatische Backups wird mindestens ein Empfänger-Schlüssel benötigt …` | Zuerst Wiederherstellungsschlüssel erzeugen |
| `Ein Backup-Ziel mit diesem Namen existiert bereits`       | Anderen Namen wählen                                |
| `Name oder Schlüssel ist bereits als Empfänger hinterlegt` | Eintrag existiert bereits                           |
| `Ungültiger Dateiname`                                     | Dateinamen prüfen                                   |

### Passwortprüfung

| Meldung                                           | Bedeutung                                      |
| ------------------------------------------------- | ---------------------------------------------- |
| `Have I Been Pwned konnte nicht erreicht werden`  | Ausgehende Verbindung prüfen (503)             |
| `Ungültige Antwort des Passwort-Prüfdienstes`     | Dienst liefert Unerwartetes (502)              |
| `Passwortprüfung momentan nicht verfügbar`        | Später erneut versuchen                        |

## Hilfe erhalten

Eröffne ein [Issue](https://github.com/CyberspaceConsulting/ClinicPulse/issues) mit Version, Betriebsart, Schritten zur Reproduktion und bereinigten Logs. Sicherheitslücken bitte per E-Mail an info@cyberspaceconsulting.de melden.
