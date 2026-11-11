# Ersteinrichtung

Nach dem Start ist die Anwendung unter `http://localhost:8080` erreichbar. Solange die Einrichtung nicht abgeschlossen ist, meldet die API den Status „Setup required“ (HTTP 401).

1. **Lizenz:** Für die Ersteinrichtung ist ein gültiger Lizenzzugang erforderlich. Der API-Dienst muss den Lizenzdienst (`CLINICPULSE_LICENSE_API_URL`) per HTTPS erreichen. Siehe [Lizenz](../features/license.md).
2. **Administrator anlegen:** Vorname, Nachname, Benutzername und Passwort des Administrators werden erfasst. Der Name lässt sich später im Profil ändern. Ein zweiter Aufruf ist nicht möglich („Initial setup is already complete“).
3. **Einrichtungsart und Bundesland:** Beides steuert verfügbare Rollen, Funktionen und Feiertage, siehe [Rollen](../features/roles-and-permissions.md) und [Arbeitszeitregeln](../features/work-rules.md).
4. **Weiteres:** Abteilungen und deren Qualifikationen anlegen. Lege fest, welche Qualifikationen zur Leitung oder Stellvertretung berechtigen, und weise diese Personen anschließend in der Abteilung zu. Danach Mitarbeitende mit Abteilung und einer oder mehreren Qualifikationen anlegen sowie Schichttypen konfigurieren. Die Teamverwaltung trennt Abteilungen, Abteilungsübersicht, Mitarbeitende und Konten/Administration. Optional [E-Mail](../features/mail.md) und [Backup](../features/backup.md) einrichten.

::: tip
Lege vor dem produktiven Einsatz einen Wiederherstellungsschlüssel an und teste eine Sicherung, siehe [Backup](../features/backup.md).
:::
