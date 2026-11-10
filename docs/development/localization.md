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
Die vom Server gelieferten Standardfunktionen werden nur in der Auswahlliste
übersetzt; ihre gespeicherten Werte und frei eingegebenen Daten bleiben erhalten.

Kataloge und Build prüfen:

```sh
cd frontend
npm run test:i18n
npm run build
```
