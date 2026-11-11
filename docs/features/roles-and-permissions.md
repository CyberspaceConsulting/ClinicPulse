# Rollen und Einrichtungsarten

Welche Zugriffsrollen und Funktionen angeboten werden, hängt von der Einrichtungsart ab. Der Katalog liegt lokal im Backend (`backend/app/role_catalog.py`) und wird nicht von einem Server geladen.

## Zugriffsrollen

Krankenhausleitung, Personaler, Oberarzt, Chefarzt, Kiosk und Mitarbeiter. Oberarzt und Chefarzt stehen nur Krankenhäusern zur Verfügung; alle anderen Einrichtungsarten bieten Leitung, Personaler, Kiosk und Mitarbeiter. Die Leitung heißt je Einrichtungsart anders (siehe Tabelle).

## Einrichtungsarten

| Einrichtungsart   | Bezeichnung der Leitung | Funktionen                                                                                   |
| ----------------- | ----------------------- | -------------------------------------------------------------------------------------------- |
| Krankenhaus       | Krankenhausleitung      | Pflegefachkraft, Arzt, Assistenzarzt, Pflegeassistenz, Hebamme, Medizinische Fachangestellte |
| Rettungsdienst    | Wachleitung             | Notfallsanitäter, Rettungssanitäter, Rettungsassistent, Rettungshelfer, Notarzt              |
| Leitstelle        | Leitstellenleitung      | Disponent, Schichtführer, Auszubildender                                                     |
| Pflegeeinrichtung | Einrichtungsleitung     | Pflegefachkraft, Pflegeassistenz, Pflegehelfer, Betreuungskraft, Hauswirtschaft              |
| Sonstige          | Leitung                 | Mitarbeiter, Teamleitung                                                                     |

## Sichtbarkeit von Dienstplänen und Abwesenheiten

Administratorkonten verwalten die Installation, erhalten aber keinen Zugriff auf Dienstpläne oder Abwesenheiten. Oberärzte sehen die Abteilungen, für die ihr Konto freigeschaltet ist. Die Krankenhausleitung kann Dienstpläne und Abwesenheiten einsehen, wenn für das Konto ausdrücklich „Dienstplan ansehen“ aktiviert wurde; standardmäßig ist dieser Zugriff ausgeschaltet.

Mitarbeitende können ihre eigenen Dienste und Abwesenheitsanfragen sehen. Die Dienstansicht „Nächste Dienste“ zeigt ihre kommenden Einsätze. Offene Besetzungslücken und Planungswarnungen werden ihnen nicht angezeigt; ihre Meldungen beziehen sich auf den Status ihrer Abwesenheitsanfragen.
