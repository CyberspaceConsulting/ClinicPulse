# Arbeitszeitregeln

ClinicPulse prüft geplante Arbeits- und Ruhezeiten. Die Prüfungen decken nicht alle gesetzlichen, tariflichen oder betrieblichen Anforderungen ab und sind keine Rechtskonformitätsgarantie.

## Einstellbare Grenzen

| Einstellung             | Standard | Zulässiger Bereich |
| ----------------------- | -------- | ------------------ |
| Ruhezeit (Stunden)      | 11       | 11–24              |
| Höchstarbeitszeit pro Tag (Stunden) | 10 | 1–10            |
| Höchstarbeitszeit pro Woche (Stunden) | 48 | 1–48          |

Der Wochenwert ist ein Durchschnitt über 24 Wochen, keine starre Wochengrenze. Die Grenzen lassen sich nur innerhalb der gesetzlichen Rahmenwerte verschärfen.

## Pausen

Ist keine Pause geplant, gilt die Mindestpause nach § 4 ArbZG:

| Arbeitszeit (ohne Pause) | Mindestpause |
| ------------------------ | ------------ |
| bis 6 Stunden            | keine        |
| mehr als 6 Stunden       | 30 Minuten   |
| mehr als 9 Stunden       | 45 Minuten   |

Die Pause muss in die Schicht passen und spätestens nach sechs Stunden beginnen.

## Betriebskonfiguration

- **Bundesland:** bestimmt die gesetzlichen Feiertage.
- **Einrichtungsart:** bestimmt Rollen und Funktionen.
- **Zeitzone:** Standard `Europe/Berlin`.
- **Sonntagsarbeit zulässig:** muss ausdrücklich aktiviert werden, sonst werden Sonntage und Feiertage als Verstoß gemeldet.

Zusätzlich muss mindestens 15 Sonntage pro Kalenderjahr arbeitsfrei bleiben (§ 11 ArbZG).

Alle Prüfungen beziehen sich auf die Person, nicht auf eine Abteilung: Arbeitet jemand in mehreren Abteilungen, werden Überschneidungen, Ruhezeiten, Tageshöchstarbeitszeit und der 24-Wochen-Durchschnitt über alle Dienste gemeinsam bewertet.

Ein Verstoß verhindert die Zuweisung (HTTP 409); die Meldung nennt die verletzte Regel.
