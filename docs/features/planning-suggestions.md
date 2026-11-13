# Planungsvorschläge

Medora kann Besetzungen vorschlagen. Vorschläge sind Entwürfe und werden erst nach einer Freigabe zu Dienstzuweisungen.

## Planungsentwurf (Optimierung)

Das Backend löst die Besetzung offener Positionen als Optimierungsproblem (OR-Tools CP-SAT). Dabei gelten:

- Abwesenheiten und die [Arbeitszeitregeln](work-rules.md) werden berücksichtigt – für Personen in mehreren Abteilungen über alle Abteilungen hinweg. Eine Person wird pro Tag höchstens einmal vorgeschlagen.
- Prioritäten: Gesetzliche Grenzen sind harte Bedingungen und werden nie zugunsten der Besetzung verletzt. Innerhalb dieser Grenzen werden zuerst möglichst viele geforderte Stellen besetzt, danach möglichst wenige Personen eingesetzt und zuletzt die Wochenbelastung ausgeglichen. Nicht besetzbare Stellen bleiben als offen sichtbar.
- Geforderte Qualifikationen sind verbindlich. Eine Person, die mehrere geforderte Qualifikationen besitzt (z. B. Arzt und Praxisanleiter), deckt mit einem Einsatz alle diese Anforderungen ab (`positions`). Bei der Krankheitsvertretung braucht dagegen jede ausgefallene Person eine eigene Vertretung.
- Grenzen: höchstens 150 offene Positionen und 5.000 Kandidatenvariablen; die Rechenzeit ist auf 3 Sekunden begrenzt, sodass nicht immer ein nachweislich optimales Ergebnis erreicht wird.
- Zeiträume sind auf 1–63 Tage begrenzt.

Ist der Zeitraum zu groß, wird er abgelehnt; wähle dann einen kürzeren Zeitraum oder eine einzelne Abteilung.

Ablauf: Vorschau anfordern, prüfen, dann freigeben. Die Freigabe erfordert das Recht „Dienstplan freigeben“ und gilt nur für die eigene Abteilung.

## Smart Selection

Für einzelne offene Positionen schlägt die Smart Selection geeignete Mitarbeitende vor. Eine Auswahl wird einzeln freigegeben und als Zuweisung angelegt.
