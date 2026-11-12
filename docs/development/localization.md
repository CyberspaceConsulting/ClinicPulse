# Lokalisierung

Die Lokalisierung befindet sich noch im Aufbau. Die Passwortkomponente, die
statischen Texte der Anmeldung, Ersteinrichtung und Einladung, die Navigation,
die Abwesenheitsoberfläche, die Planungsvorschau, die Wochen- und Tagesansicht
des Dienstplans, Formulare für Dienste und Mitarbeitende, Teile der
Teamverwaltung, Benachrichtigungen, Profil, Archiv, SMTP-Einstellungen und die Backup-Oberfläche
sind teilweise übersetzt. Einige
bekannte API-Fehler werden ebenfalls übersetzt. API-Fehler, Sicherungs- und
Einstellungshinweise sowie Hinweise der Teamverwaltung werden beim Sprachwechsel
neu dargestellt. Der Sprachumschalter ist vor
und nach der Anmeldung verfügbar. Bei Englisch weist er darauf hin, dass die
übrige Oberfläche und API-Meldungen noch nicht vollständig übersetzt sind.

Die Kataloge liegen in `frontend/src/i18n/locales/de.js` und `en.js`. Schlüssel
sind nach Bereich benannt. Texte für neue oder migrierte Oberflächenelemente
gehören in beide Kataloge und werden mit `t('bereich.schluessel')` aus
`frontend/src/i18n` ausgegeben. Variablen werden mit Platzhaltern wie
`{count}` und `t('schluessel', { count })` eingefügt. Die Texte werden als
normaler Text gerendert, nicht als HTML.

### Begriffe je Einrichtungsart

Die Bezeichnung der Organisationseinheit hängt von der Einrichtungsart ab
(Abteilung, Standort, Leitstelle oder frei gewählt). Texte, die diese Bezeichnung
enthalten, verwenden deshalb Platzhalter statt des festen Worts. Sie werden in
`frontend/src/i18n/terms.ts` aufgelöst, ohne dass beim Aufruf von `t` Werte
übergeben werden müssen. Ein großer erster Buchstabe im Platzhalter schreibt das
Ergebnis groß (`{Unit}` statt `{unit}`).

| Deutsch                                                                 | Englisch                              |
| ----------------------------------------------------------------------- | ------------------------------------- |
| `{unit}`, `{units}`: Einzahl, Mehrzahl                                  | `{unit}`, `{units}`; klein `{unitl}`, `{unitsl}` |
| `{unitc}`, `{unitcl}`: Wortbestandteil („Abteilungs“ für `…leitung`)    | –                                     |
| `{unith}`: „Hauptabteilung“                                             | –                                     |
| Mit Artikel je Fall: `{the_unit}`, `{the_unith}`, `{a_unit}`, `{a_unit_nom}`, `{your_unit}`, `{your_own_unit}`, `{your_unit_dat}`, `{my_unit}`, `{this_unit}`, `{this_unit_gen}`, `{no_unit}`, `{no_unit_dat}`, `{the_same_unit_dat}`, `{to_unit}`, `{a_smaller_unit}` | `{a_unit}` („a/an …“)                 |

Die deutschen Artikel richten sich nach dem grammatischen Geschlecht der Bezeichnung
(bei „Sonstige“ vom Administrator gewählt). Neue Texte mit der Organisationseinheit
sollen diese Platzhalter nutzen; der Katalogtest prüft, dass jeder Platzhalter für
seine Sprache definiert ist, und ignoriert sie beim Abgleich der Sprachen.

`locale` ist eine reaktive Vue-Referenz. Die Einstellung wird unter
`clinicpulse-locale` lokal im Browser gespeichert und setzt das `lang`-Attribut
des Dokuments. Deutsch bleibt die Standardeinstellung; unbekannte Werte werden
als Deutsch behandelt. `t` ist reaktiv, wenn es während eines Renderings oder
innerhalb von `computed` aufgerufen wird. Einmalig außerhalb davon ausgewertete
Übersetzungen aktualisieren sich bei einem Sprachwechsel nicht.

Um eine weitere Sprache vorzubereiten, einen vollständigen Katalog mit
denselben Schlüsseln und Platzhaltern anlegen, ihn in
`frontend/src/i18n/index.ts` registrieren und die Katalogtests entsprechend
erweitern. Außerdem einen Eintrag in `localeOptions` und den Namen im
Sprachkatalog ergänzen. Weitere
Sprachen sollen erst angeboten werden, wenn alle UI-Texte, Standardrollen
und bekannten API-Meldungen übersetzt und überprüft sind. Frei eingegebene
Daten dürfen nicht übersetzt werden. Bekannte API-Fehlermeldungen werden in
`frontend/src/i18n/apiErrors.ts` Katalogschlüsseln zugeordnet. Unbekannte
Meldungen bleiben unverändert sichtbar und erhalten bei Englisch eine
übersetzte Einleitung. `ApiError` speichert den ursprünglichen Antwortinhalt
und HTTP-Status; `errorMessage` übersetzt erst bei der Anzeige. Auch
`TranslatedError` speichert Schlüssel und Parameter statt eines bereits
übersetzten Textes. So bleiben angezeigte Fehler beim Sprachwechsel aktuell.
Für Validierungsfehler mit dem Pydantic-Präfix `Value error, ` wird dieses
nur bei bekannten Meldungen entfernt. Dynamische Backup- und
Planungsmeldungen werden anhand ihrer festen Form erkannt; Feldnamen,
Fehlerdetails, Schichtnamen und Datumswerte bleiben dabei erhalten.
Übliche Pydantic-Validierungsfehler werden anhand ihres Typs und ihrer
Grenzwerte übersetzt; unbekannte Meldungen bleiben mit ihren Originaldetails
sichtbar.
Die vom Server gelieferten Standardfunktionen werden nur in der Auswahlliste
übersetzt; ihre gespeicherten Werte und frei eingegebenen Daten bleiben erhalten.

Kataloge und Build prüfen:

```sh
cd frontend
npm run test:i18n
npm run build
```
