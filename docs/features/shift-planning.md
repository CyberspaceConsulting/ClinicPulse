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
| Pause / Pausenbeginn  | 0–240 Minuten bzw. 0–360 Minuten nach Schichtbeginn        |

Eine Schichtart kann mehrere Funktionen mit jeweils eigener Soll-Besetzung enthalten. Dazu gehört auch „Oberarzt“ als eigene Funktion; diese Stelle wird bei der Soll-Besetzung berücksichtigt und kann nur mit Mitarbeitenden besetzt werden, deren Funktion „Oberarzt“ ist. Bei manueller Besetzung werden für qualifikationsgebundene Stellen nur passende Mitarbeitende angeboten. Bestehende Schichtarten mit einer Funktion werden entsprechend weitergeführt. Oberärzte und Dienstplaner können Schichtarten nachträglich bearbeiten. Eine Schichtart, der bereits Dienste zugewiesen sind, kann nicht gelöscht werden („Shift type is in use“).

Wird keine Pause angegeben, setzt ClinicPulse die gesetzliche Mindestpause (siehe [Arbeitszeitregeln](work-rules.md)).

## Dienstzuweisungen

Eine Zuweisung verbindet Mitarbeitenden und Schichttyp mit einem Zeitraum (mit Zeitzone). Das Ende muss nach dem Beginn liegen. Beim Anlegen prüft das System:

- Mitarbeitender und Schicht gehören zur selben Abteilung.
- Keine Überschneidung mit einer anderen Schicht des Mitarbeitenden.
- Keine Abwesenheit im Zeitraum.
- Die Schicht ist nicht bereits voll besetzt.
- Die [Arbeitszeitregeln](work-rules.md) werden eingehalten.

Verstöße werden als HTTP 409 mit einer Erklärung abgelehnt, siehe [Fehlerbehebung](../troubleshooting.md).

## Berechtigungen

Ansehen, Bearbeiten und Freigeben sind getrennte Rechte. Die Smart-Auswahl und Planungsvorschläge sind Dienstplanern mit Bearbeitungsrecht vorbehalten. Dienstpläne und Abwesenheiten sind für den Administrator nicht einsehbar. Die Krankenhausleitung erhält diese Leserechte nur, wenn „Dienstplan ansehen“ für ihr Konto aktiviert ist. Oberärzte sehen nur die ihnen zugewiesenen Abteilungen; Mitarbeitende sehen im Dienstplan nur ihre eigenen Dienste und keine offenen Besetzungslücken. Chefärzte sind schreibgeschützt.
