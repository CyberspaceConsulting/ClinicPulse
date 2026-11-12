# Internationalisierung

ClinicPulse erhält eine erweiterbare Sprachunterstützung für seine Oberfläche.
Die Einstellung gilt für den jeweiligen Browser und ändert weder gespeicherte
Personen- und Abteilungsnamen noch andere selbst eingegebene Inhalte.

Die Bezeichnung der Organisationseinheit richtet sich nach der Einrichtungsart und ändert sich in der gesamten Oberfläche (z. B. „Standort“ beim Rettungsdienst, „Leitstelle“ bei der ILS, frei gewählt bei „Sonstige“); sie gilt in beiden Sprachen. Details für Entwickelnde: [Lokalisierung](../development/localization.md).

::: warning Übersetzung noch nicht vollständig
Deutsch ist die Standardsprache. Englisch ist verfügbar, aber noch nicht für
alle Bereiche übersetzt. Insbesondere Formulare, Verwaltung, Einstellungen und
Meldungen der API können weiterhin deutschen oder englischen Originaltext
enthalten. Die Anwendung weist bei der Auswahl von Englisch darauf hin.
:::

## Sprache auswählen

Die Sprachauswahl mit Flagge befindet sich auf den Anmelde- und
Einrichtungsseiten sowie nach der Anmeldung in der oberen Leiste. Wähle
**Deutsch** oder **English** aus der Liste. Bereits übersetzte Texte und das
Sprachmerkmal der Seite ändern sich sofort; ein Neuladen ist nicht nötig.

Die Auswahl wird im `localStorage` dieses Browsers unter `clinicpulse-locale`
gespeichert. Andere Browser oder Geräte übernehmen sie nicht automatisch.
Wird die Auswahl gelöscht oder enthält sie einen nicht unterstützten Wert,
verwendet ClinicPulse Deutsch.

| Code | Sprache | Stand |
| --- | --- | --- |
| `de` | Deutsch | Standardsprache |
| `en` | English | Teilübersetzung; weitere Bereiche folgen |

Die Dokumentationsseite selbst ist zurzeit auf Deutsch verfügbar und hat
keine separate Sprachauswahl. Die Anwendungseinstellung verändert die
Dokumentationssprache nicht.

## Übersetzungen beitragen

Die Anwendungstexte stehen in den Katalogen unter
`frontend/src/i18n/locales/`. Neue UI-Texte gehören in beide Sprachdateien;
Schlüssel und Platzhalter wie `{name}` müssen übereinstimmen.
Die [Entwicklungsanleitung](../development/localization.md) beschreibt,
wie Übersetzungen verwendet, weitere Sprachen registriert und die Kataloge
geprüft werden.

Frei eingegebene Daten dürfen nicht automatisch übersetzt werden. Bei nicht
vorhersehbaren Fehlermeldungen externer Systeme soll der Originaltext erhalten
bleiben, ergänzt um eine übersetzte Einleitung.
