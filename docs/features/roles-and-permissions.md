# Rollen und Einrichtungsarten

Welche Zugriffsrollen und Funktionen angeboten werden, hängt von der Einrichtungsart ab. Der Katalog liegt lokal im Backend (`backend/app/role_catalog.py`) und wird nicht von einem Server geladen.

## Zugriffsrollen und Abteilungsqualifikationen

Zugriffsrollen steuern den Systemzugang: Krankenhausleitung, Personaler, Oberarzt, Chefarzt, Kiosk und Mitarbeiter. Oberarzt und Chefarzt stehen nur Krankenhäusern zur Verfügung; alle anderen Einrichtungsarten bieten Leitung, Personaler, Kiosk und Mitarbeiter. Die Leitung heißt je Einrichtungsart anders (siehe Tabelle).

Davon getrennt verwaltet jede Abteilung ihre eigenen Qualifikationen, zum Beispiel „Arzt“, „Pflege“ oder „Oberarzt“. Mitarbeitende können mehrere Qualifikationen innerhalb ihrer Abteilung haben. Diese Qualifikationen bestimmen, für welche Funktionen sie in Schichten eingeplant werden können; sie ersetzen keine Zugriffsrolle.

## Abteilungsleitung und Stellvertretung

Eine berechtigte Person wird in der Abteilungsverwaltung als Leitung oder optional als Stellvertretung eingetragen. Dafür muss sie eine in der Abteilung als leitungsberechtigt markierte Qualifikation haben. Die Eintragung gewährt Verwaltungsrechte ausschließlich für diese Abteilung: Abteilung und Qualifikationen bearbeiten, Mitarbeitende verwalten und Mitarbeiterkonten anlegen oder verwalten. Leitung und Stellvertretung können außerdem die Abteilung planen und Vorschläge freigeben. Die Rolle „Oberarzt“ allein verleiht keine Abteilungsverwaltungsrechte.

Die Teamverwaltung ist in die Bereiche **Abteilungen**, **Abteilungsübersicht**, **Mitarbeitende** und **Konten & Administration** gegliedert. Welche Bereiche sichtbar und bearbeitbar sind, richtet sich nach der Zugriffsrolle und den zugewiesenen Abteilungsrechten.

## Einrichtungsarten

| Einrichtungsart   | Bezeichnung der Leitung | Organisationseinheit              | Funktionen                                                                                   |
| ----------------- | ----------------------- | --------------------------------- | -------------------------------------------------------------------------------------------- |
| Krankenhaus       | Krankenhausleitung      | Abteilungen                       | Pflegefachkraft, Arzt, Assistenzarzt, Pflegeassistenz, Hebamme, Medizinische Fachangestellte |
| Rettungsdienst    | Wachleitung             | **Standorte** mit Fahrzeugen      | Notfallsanitäter, Rettungssanitäter, Rettungsassistent, Rettungshelfer, Notarzt              |
| Leitstelle        | Leitstellenleitung      | genau eine Leitstelle             | Disponent, Schichtführer, Auszubildender                                                     |
| Pflegeeinrichtung | Einrichtungsleitung     | Abteilungen                       | Pflegefachkraft, Pflegeassistenz, Pflegehelfer, Betreuungskraft, Hauswirtschaft              |
| Sonstige          | frei wählbar            | frei wählbar                      | Mitarbeiter, Teamleitung                                                                     |

Die Einrichtungsart kommt aus der Lizenz und bestimmt auch die Begriffe der Oberfläche: Beim Rettungsdienst heißt „Abteilung“ überall „Standort“ (z. B. „Standort anlegen“, „Standortleitung“), bei der Leitstelle „Leitstelle“. Für „Sonstige“ legt der Administrator Bezeichnung (Einzahl, Mehrzahl, grammatisches Geschlecht), Leitungsbezeichnung, Struktur und Fahrzeugnutzung in der Ersteinrichtung fest und kann sie unter Einstellungen → Betrieb ändern. In zusammengesetzten Wörtern wird die Bezeichnung ohne Fugen-s angehängt („Bereichleitung“); wähle bei Bedarf eine Bezeichnung, die so natürlich klingt.

### Rettungsdienst: Standorte und Fahrzeuge

Jeder Standort (Wache) verwaltet seine Fahrzeuge mit Typ (RTW, NEF, KTW, ITW, ELW, MTW, Sonstige) und Kennung. Eine Schichtart gehört optional zu einem Fahrzeug desselben Standorts; beim Anlegen wird die Besetzung nach Fahrzeugtyp vorbelegt (z. B. RTW: Notfallsanitäter und Rettungssanitäter, NEF: Notarzt und Notfallsanitäter, KTW: Rettungssanitäter und Rettungshelfer) und lässt sich anpassen. Der Dienstplan ist nach Fahrzeug gruppiert.

Ein defektes Fahrzeug wird auf **Deaktiviert** gestellt: Für seine Schichten werden keine offenen Stellen mehr gezählt, vorgeschlagen oder zugewiesen („Vehicle is deactivated“). Bereits geplante Dienste bleiben bestehen und müssen bei Bedarf manuell umgeplant werden. Ein Fahrzeug, das noch Schichten hat, kann nicht gelöscht, aber deaktiviert werden. Fahrzeuge verwalten Konten mit Bearbeitungsrecht, Leitungen und Stellvertretungen, das Management und Administratoren – bei begrenzten Rechten nur für die zugewiesenen Standorte. Kiosk-Konten verwalten keine Fahrzeuge; sehen können Fahrzeuge alle Konten im Rahmen ihrer Standorte.

### Leitstelle

Bei der Leitstelle gibt es genau eine Organisationseinheit. Sie wird bei der Ersteinrichtung mit dem eingegebenen Namen angelegt; Anlegen weiterer Einheiten und Löschen der Leitstelle sind nicht möglich („This facility type uses a single organizational unit“), Umbenennen sowie Qualifikationen und Leitung bearbeiten schon. Bestehende Installationen ohne Einheit können die erste anlegen.

## Sichtbarkeit von Dienstplänen und Abwesenheiten

Administratorkonten verwalten die Installation, erhalten aber keinen Zugriff auf Dienstpläne oder Abwesenheiten. Oberärzte sehen die Abteilungen, für die ihr Konto freigeschaltet ist. Die Krankenhausleitung kann Dienstpläne und Abwesenheiten einsehen, wenn für das Konto ausdrücklich „Dienstplan ansehen“ aktiviert wurde; standardmäßig ist dieser Zugriff ausgeschaltet.

Mitarbeitende können ihre eigenen Dienste und Abwesenheitsanfragen sehen. Die Dienstansicht „Nächste Dienste“ zeigt ihre kommenden Einsätze. Offene Besetzungslücken und Planungswarnungen werden ihnen nicht angezeigt; ihre Meldungen beziehen sich auf den Status ihrer Abwesenheitsanfragen.

Leitungs-, Personal- und Arztkonten können in der Teamverwaltung optional mit einem Mitarbeitendeneintrag verknüpft werden. Dadurch erhalten sie Zugriff auf ihre eigenen Abwesenheiten, auch ohne Dienstplanzugriff; ihre sonstigen Berechtigungen bleiben unverändert. Administrator- und Kiosk-Konten können nicht verknüpft werden.

Ein Administrator kann weitere Administratorkonten anlegen und je Abteilung Leitung sowie Stellvertretung zuweisen. Mitarbeitendenkonten können außerdem von Personalverantwortlichen und den für die Abteilung eingetragenen Leitungen oder Stellvertretungen verwaltet werden. Diese Abteilungsrechte gelten nur für die jeweils zugewiesene Abteilung; sie gewähren keine Rechte für andere Abteilungen oder die gesamte Einrichtung. Neue Urlaubsanträge werden berechtigten Dienstplanverantwortlichen zusätzlich als Hinweisfenster angezeigt.
