# Rollen und Einrichtungsarten

Welche Zugriffsrollen und Funktionen angeboten werden, hängt von der Einrichtungsart ab. Der Katalog liegt lokal im Backend (`backend/app/role_catalog.py`) und wird nicht von einem Server geladen.

## Zugriffsrollen und Abteilungsqualifikationen

Zugriffsrollen steuern den Systemzugang: Krankenhausleitung, Personaler, Oberarzt, Chefarzt, Kiosk und Mitarbeiter. Oberarzt und Chefarzt stehen nur Krankenhäusern zur Verfügung; alle anderen Einrichtungsarten bieten Leitung, Personaler, Kiosk und Mitarbeiter. Die Leitung heißt je Einrichtungsart anders (siehe Tabelle).

Davon getrennt verwaltet jede Abteilung ihre eigenen Qualifikationen, zum Beispiel „Arzt“, „Pflege“ oder „Oberarzt“. Mitarbeitende können mehrere Qualifikationen innerhalb ihrer Abteilung haben. Diese Qualifikationen bestimmen, für welche Funktionen sie in Schichten eingeplant werden können; sie ersetzen keine Zugriffsrolle.

## Abteilungsleitung und Stellvertretung

Eine berechtigte Person wird in der Abteilungsverwaltung als Leitung oder optional als Stellvertretung eingetragen. Dafür muss sie eine in der Abteilung als leitungsberechtigt markierte Qualifikation haben. Die Eintragung gewährt Verwaltungsrechte ausschließlich für diese Abteilung: Abteilung und Qualifikationen bearbeiten, Mitarbeitende verwalten und Mitarbeiterkonten anlegen oder verwalten. Leitung und Stellvertretung können außerdem die Abteilung planen und Vorschläge freigeben. Die Rolle „Oberarzt“ allein verleiht keine Abteilungsverwaltungsrechte.

Die Teamverwaltung ist in die Bereiche **Abteilungen**, **Abteilungsübersicht**, **Mitarbeitende** und **Konten & Administration** gegliedert. Welche Bereiche sichtbar und bearbeitbar sind, richtet sich nach der Zugriffsrolle und den zugewiesenen Abteilungsrechten.

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

Leitungs-, Personal- und Arztkonten können in der Teamverwaltung optional mit einem Mitarbeitendeneintrag verknüpft werden. Dadurch erhalten sie Zugriff auf ihre eigenen Abwesenheiten, auch ohne Dienstplanzugriff; ihre sonstigen Berechtigungen bleiben unverändert. Administrator- und Kiosk-Konten können nicht verknüpft werden.

Ein Administrator kann weitere Administratorkonten anlegen und je Abteilung Leitung sowie Stellvertretung zuweisen. Mitarbeitendenkonten können außerdem von Personalverantwortlichen und den für die Abteilung eingetragenen Leitungen oder Stellvertretungen verwaltet werden. Diese Abteilungsrechte gelten nur für die jeweils zugewiesene Abteilung; sie gewähren keine Rechte für andere Abteilungen oder die gesamte Einrichtung. Neue Urlaubsanträge werden berechtigten Dienstplanverantwortlichen zusätzlich als Hinweisfenster angezeigt.
