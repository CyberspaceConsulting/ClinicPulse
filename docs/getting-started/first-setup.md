# Ersteinrichtung

Nach dem Start ist die Anwendung unter `http://localhost:8080` erreichbar. Solange die Einrichtung nicht abgeschlossen ist, meldet die API den Status „Setup required“ (HTTP 401).

Nach der Anmeldung öffnet sich für Administratorkonten eine eigene Übersichtsseite mit Direktzugriff auf Teamverwaltung und zentrale Einstellungen wie Betrieb, E-Mail, Lizenz, Backups und Sicherheit.

1. **Lizenz:** Für die Ersteinrichtung ist ein gültiger Lizenzzugang erforderlich. Der API-Dienst muss den Lizenzdienst (`MEDORA_LICENSE_API_URL`) per HTTPS erreichen. Siehe [Lizenz](../features/license.md).
2. **Administrator anlegen:** Vorname, Nachname, Benutzername und Passwort des Administrators werden erfasst. Der Name lässt sich später im Profil ändern. Ein zweiter Aufruf ist nicht möglich („Initial setup is already complete“).
3. **Einrichtungsart und Bundesland:** Beides steuert verfügbare Rollen, Funktionen, Begriffe und Feiertage, siehe [Rollen](../features/roles-and-permissions.md#einrichtungsarten) und [Arbeitszeitregeln](../features/work-rules.md). Die Einrichtungsart kommt normalerweise aus der Lizenz. Je nach Einrichtungsart verlangt die Ersteinrichtung weitere Angaben:
   - **Leitstelle (ILS):** Name der Hauptleitstelle (z. B. „Leitstelle Nord“). Sie wird automatisch als einzige Organisationseinheit angelegt.
   - **Sonstige:** Bezeichnung der Organisationseinheit (Einzahl und Mehrzahl, z. B. „Bereich“/„Bereiche“), grammatisches Geschlecht für die deutschen Texte, Bezeichnung der Leitung sowie ob es nur eine Einheit gibt (dann zusätzlich deren Name) und ob Fahrzeuge verwaltet werden. Das lässt sich später unter Einstellungen → Betrieb ändern.
4. **Weiteres:** Abteilungen (beim Rettungsdienst: Standorte) und deren Qualifikationen anlegen. Lege fest, welche Qualifikationen zur Leitung oder Stellvertretung berechtigen, und weise diese Personen anschließend in der Abteilung zu. Danach Mitarbeitende mit Abteilung und einer oder mehreren Qualifikationen anlegen sowie Schichttypen konfigurieren. Beim Rettungsdienst zuvor je Standort die Fahrzeuge anlegen. Die Teamverwaltung trennt Abteilungen, Abteilungsübersicht, Mitarbeitende und Konten/Administration. Optional [E-Mail](../features/mail.md) und [Backup](../features/backup.md) einrichten.

::: tip
Lege vor dem produktiven Einsatz einen Wiederherstellungsschlüssel an und teste eine Sicherung, siehe [Backup](../features/backup.md).
:::
