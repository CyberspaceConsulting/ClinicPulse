# Abteilungen und Mitarbeitende

## Abteilungen

Abteilungen gliedern Teams und begrenzen, was Konten sehen und planen dürfen. Je nach [Einrichtungsart](roles-and-permissions.md#einrichtungsarten) heißen sie „Standorte“ (Rettungsdienst), „Leitstelle“ (genau eine, ILS) oder frei gewählt („Sonstige“). Namen sind eindeutig („Department name already exists“). Eine Abteilung, die noch verwendet wird (Mitarbeitende, Schichten oder Fahrzeuge), kann nicht gelöscht werden („Department is still in use“).

Konten mit Rolle in einer Abteilung dürfen nur die eigene Abteilung planen und freigeben.

## Mitarbeitende

- Mitarbeitende haben eine **Hauptabteilung** und können zusätzlich **weiteren Abteilungen** angehören. Qualifikationen gehören zur jeweiligen Abteilung; eine Person kann Qualifikationen mehrerer ihrer Abteilungen tragen (z. B. „Arzt“ in zwei Abteilungen oder „Praxisanleiter“ nur in einer). Für eine Schicht zählen nur Qualifikationen der Abteilung der Schicht.
- Die Hauptabteilung entscheidet über Abwesenheitsanträge. Planende anderer Abteilungen sehen nur genehmigte Abwesenheiten der Person, um darum herum zu planen.
- Zuordnungen verwalten nur Personen mit Verwaltungsrecht der jeweiligen Abteilung. Eine Abteilungsleitung kann nur Abteilungen hinzufügen oder entfernen, für die sie selbst Verwaltungsrechte hat, und nur Qualifikationen der eigenen Abteilung ändern. Name und Hauptabteilung ändert nur die Hauptabteilung. Zuordnungen anderer Abteilungen bleiben dabei unverändert und für die Leitung unsichtbar.
- Eine Abteilung kann nicht entfernt werden, solange die Person dort Dienste hat; eine Abteilung mit zugeordneten Personen kann nicht gelöscht werden.
- Ein Mitarbeitender mit verknüpftem Login-Konto oder geplanten Schichten kann nicht gelöscht werden.
- Über das Onboarding lässt sich ein Mitarbeitender gemeinsam mit einem Konto anlegen; bestehende Mitarbeitende können später ein Konto erhalten (ein zweites Konto wird abgelehnt: „Employee already has an account“). Das Konto einer Person mit der Rolle „Mitarbeiter“ erhält beim Anlegen oder Bearbeiten der Person Zugriff auf alle ihre Abteilungen, damit sie ihre Dienste dort sieht. Bei manuell angelegten Konten werden die Abteilungen in der Kontoverwaltung gewählt.
- Schichten können nur mit Mitarbeitenden besetzt werden, die der Abteilung der Schicht angehören. Überschneidungen, Ruhezeiten und Höchstarbeitszeiten werden über **alle** Abteilungen der Person hinweg geprüft; Dienste anderer Abteilungen sehen Planende dabei nicht, erhalten aber die jeweilige Konfliktmeldung.
