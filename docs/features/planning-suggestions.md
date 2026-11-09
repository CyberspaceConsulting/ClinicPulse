# Planungsvorschläge

ClinicPulse kann Besetzungen vorschlagen. Vorschläge sind Entwürfe und werden erst nach einer Freigabe zu Dienstzuweisungen.

## Planungsentwurf (Optimierung)

Das Backend löst die Besetzung offener Positionen als Optimierungsproblem (OR-Tools CP-SAT). Dabei gelten:

- Abwesenheiten und die [Arbeitszeitregeln](work-rules.md) werden berücksichtigt.
- Passende Funktionen werden bevorzugt (`role_match`).
- Grenzen: höchstens 150 offene Positionen und 5.000 Kandidatenvariablen; die Rechenzeit ist auf 3 Sekunden begrenzt.
- Zeiträume sind auf 1–63 Tage begrenzt.

Ist der Zeitraum zu groß, wird er abgelehnt; wähle dann einen kürzeren Zeitraum oder eine einzelne Abteilung.

Ablauf: Vorschau anfordern, prüfen, dann freigeben. Die Freigabe erfordert das Recht „Dienstplan freigeben“ und gilt nur für die eigene Abteilung.

## Smart Selection

Für einzelne offene Positionen schlägt die Smart Selection geeignete Mitarbeitende vor. Eine Auswahl wird einzeln freigegeben und als Zuweisung angelegt.
