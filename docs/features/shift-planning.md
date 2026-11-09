# Dienstplanung

## Schichttypen

Ein Schichttyp beschreibt eine wiederkehrende Schicht:

| Feld                  | Bedeutung                                                  |
| --------------------- | ---------------------------------------------------------- |
| Name                  | eindeutig, 1–80 Zeichen                                    |
| Beginn / Ende         | Uhrzeiten; endet die Schicht vor dem Beginn, geht sie über Mitternacht |
| Farbe                 | Hexwert, z. B. `#2563eb`                                   |
| Position              | benötigte Funktion, z. B. Pflegefachkraft                  |
| Soll-Besetzung        | 1–100 Personen                                             |
| Abteilung             | optional                                                   |
| Pause / Pausenbeginn  | 0–240 Minuten bzw. 0–360 Minuten nach Schichtbeginn        |

Wird keine Pause angegeben, setzt ClinicPulse die gesetzliche Mindestpause (siehe [Arbeitszeitregeln](work-rules.md)). Ein Schichttyp, der verwendet wird, kann nicht gelöscht werden („Shift type is in use“).

## Dienstzuweisungen

Eine Zuweisung verbindet Mitarbeitenden und Schichttyp mit einem Zeitraum (mit Zeitzone). Das Ende muss nach dem Beginn liegen. Beim Anlegen prüft das System:

- Mitarbeitender und Schicht gehören zur selben Abteilung.
- Keine Überschneidung mit einer anderen Schicht des Mitarbeitenden.
- Keine Abwesenheit im Zeitraum.
- Die Schicht ist nicht bereits voll besetzt.
- Die [Arbeitszeitregeln](work-rules.md) werden eingehalten.

Verstöße werden als HTTP 409 mit einer Erklärung abgelehnt, siehe [Fehlerbehebung](../troubleshooting.md).

## Berechtigungen

Ansehen, Bearbeiten und Freigeben sind getrennte Rechte. Dienstpläne sind für den Administrator nicht einsehbar. Chefärzte sind schreibgeschützt.
