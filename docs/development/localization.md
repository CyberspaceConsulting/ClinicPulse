# Lokalisierung

Die Lokalisierung befindet sich noch im Aufbau. Die Passwortkomponente, die
statischen Texte der Anmeldung, Ersteinrichtung und Einladung sowie die
Navigation sind übersetzt. Ein Sprachumschalter ist noch nicht freigegeben;
die übrige Oberfläche und API-Meldungen sind nicht vollständig übersetzt.

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
erweitern. Bevor die Sprache in einem Umschalter angeboten wird, müssen alle
UI-Texte, Standardrollen und bekannten API-Meldungen übersetzt und überprüft
sein. Frei eingegebene Daten dürfen nicht übersetzt werden. Nicht vorhersagbare
externe Fehlermeldungen sollen mit übersetzter Einleitung und unverändertem
Original angezeigt werden.

Kataloge und Build prüfen:

```sh
cd frontend
npm run test:i18n
npm run build
```
