# Dienstplanung

## Schichttypen

Ein Schichttyp beschreibt eine wiederkehrende Schicht:

| Feld                  | Bedeutung                                                  |
| --------------------- | ---------------------------------------------------------- |
| Name                  | eindeutig, 1–80 Zeichen                                    |
| Beginn / Ende         | Uhrzeiten; endet die Schicht vor dem Beginn, geht sie über Mitternacht |
| Farbe                 | Hexwert, z. B. `#2563eb`                                   |
| Soll-Besetzung        | 1–100 Personen je Funktion, z. B. 3 Ärzte und 10 Pflegekräfte |
| Abteilung             | optional                                                   |
| Fahrzeug              | nur Rettungsdienst (bzw. „Sonstige“ mit Fahrzeugen), optional, muss zum Standort gehören |
| Pause / Pausenbeginn  | 0–240 Minuten bzw. 0–360 Minuten nach Schichtbeginn        |

Eine Schichtart kann mehrere abteilungsspezifische Qualifikationen mit jeweils eigener Soll-Besetzung enthalten, z. B. „2 × Arzt“ und „1 × Praxisanleiter“. Qualifikationen sind **verbindlich**: Es werden nur Mitarbeitende eingeplant oder vorgeschlagen, die mindestens eine geforderte Qualifikation der Schicht-Abteilung besitzen. Eine Person zählt für **jede** geforderte Qualifikation, die sie erfüllt. Ist sie gleichzeitig Arzt und Praxisanleiter, deckt sie beide Anforderungen ab; ohne qualifizierte Person bleibt die Stelle offen. Die Obergrenze je Qualifikation wird bei Schichten mit mehreren Anforderungen und bei „Oberarzt“ geprüft. Bereits gespeicherte Dienste werden nicht verändert. Dienstplanverantwortliche der Abteilung können Schichtarten nachträglich bearbeiten. Eine Schichtart, der bereits Dienste zugewiesen sind, kann nicht gelöscht werden („Shift type is in use“).

Wird keine Pause angegeben, setzt Medora die gesetzliche Mindestpause (siehe [Arbeitszeitregeln](work-rules.md)).

## Dienstzuweisungen

Eine Zuweisung verbindet Mitarbeitenden und Schichttyp mit einem Zeitraum (mit Zeitzone). Das Ende muss nach dem Beginn liegen. Beim Anlegen prüft das System:

- Mitarbeitender gehört zur Abteilung der Schicht (Haupt- oder weitere Abteilung) und besitzt eine dort geforderte Qualifikation.
- Keine Überschneidung mit einer anderen Schicht des Mitarbeitenden – auch nicht in einer anderen Abteilung.
- Keine Abwesenheit im Zeitraum.
- Die Schicht ist nicht bereits voll besetzt.
- Die [Arbeitszeitregeln](work-rules.md) werden eingehalten, wobei alle Dienste der Person in allen Abteilungen zählen.

Verstöße werden als HTTP 409 mit einer Erklärung abgelehnt, siehe [Fehlerbehebung](../troubleshooting.md).
Auch Planungsvorschläge schließen Personen mit bereits gespeicherten überschneidenden Diensten aus. Bei der Freigabe werden die Regeln erneut geprüft.

## Berechtigungen

Ansehen, Bearbeiten und Freigeben sind getrennte Rechte. Die Smart-Auswahl und Planungsvorschläge sind Dienstplanverantwortlichen mit Bearbeitungsrecht vorbehalten. Leitung und Stellvertretung erhalten diese Rechte für ihre zugewiesene Abteilung. Die Systemrolle „Oberarzt“ allein verleiht keine Abteilungsverwaltungsrechte. Dienstpläne und Abwesenheiten sind für den Administrator nicht einsehbar. Die Krankenhausleitung erhält diese Leserechte nur, wenn „Dienstplan ansehen“ für ihr Konto aktiviert ist. Mitarbeitende sehen im Dienstplan nur ihre eigenen Dienste und keine offenen Besetzungslücken. Chefärzte sind schreibgeschützt.

## Krankheitsvertretung

Nach einer Krankmeldung ermittelt die Startseite für betroffene, bereits geplante Dienste geeignete Ersatzvorschläge. Dabei braucht jede ausgefallene Person eine eigene Vertretung mit der Qualifikation für die Anforderung, die sie in der Schicht erfüllt hat; erfüllte sie mehrere (z. B. Arzt und Praxisanleiter), gilt die mit der kleinsten Soll-Besetzung. Arbeitet die erkrankte Person in mehreren Abteilungen, sehen Planende jeder dieser Abteilungen die Krankmeldung und erhalten Vorschläge für die Dienste ihrer eigenen Abteilung; Dienste anderer Abteilungen bleiben unsichtbar. Leitende Personen können die Vorschläge neu berechnen und bei Bedarf eine andere vorgeschlagene Person auswählen. Erst nach ausdrücklicher Bestätigung werden die bisherigen Zuweisungen durch die Ersatzzuweisungen ersetzt; Arbeitszeit-, Abwesenheits-, Qualifikations- und Überschneidungsregeln werden dabei erneut geprüft. Nicht besetzbare Dienste bleiben unverändert und werden als ohne passenden Vorschlag angezeigt.

## Startseite

Nach Anmeldung und beim Wiederherstellen einer Sitzung öffnet Medora zuverlässig die Übersicht. Mitarbeitende sehen dort den nächsten Dienst, eine Wochenübersicht und den Einstieg zum Abwesenheitsantrag. Leitende Personen sehen zusätzlich offene Abwesenheitsanträge und gegebenenfalls Krankheitsvertretungen. Administratorkonten erhalten eine eigene Startseite mit Verknüpfungen zu Teamverwaltung, Betrieb, E-Mail, Lizenz, Backups, Sicherheit, Audit-Protokoll und Archivierung.
