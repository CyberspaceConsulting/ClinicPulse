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
