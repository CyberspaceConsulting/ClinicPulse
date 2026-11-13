# Lizenz

Für die Ersteinrichtung und den Betrieb ist ein gültiger Lizenzzugang erforderlich. Der API-Dienst prüft die Lizenz über den Lizenzdienst (`MEDORA_LICENSE_API_URL`, HTTPS) und validiert signierte Tokens mit einem öffentlichen RSA-Schlüssel (mind. 2048 Bit).

## Verhalten

| Zustand                        | Auswirkung                                                              |
| ------------------------------ | ----------------------------------------------------------------------- |
| aktiv                          | normaler Betrieb                                                        |
| nicht aktiv / gesperrt         | Zugriff wird abgelehnt (HTTP 403)                                       |
| Lizenzserver nicht erreichbar  | Prüfung nicht möglich (HTTP 503); ein bereits gespeicherter Token gilt weiter |
| Kulanzzeit abgelaufen          | Nur-Lesen-Modus: schreibende Aktionen werden mit HTTP 423 abgelehnt     |
| Benutzerlimit erreicht         | weitere Konten werden abgelehnt (HTTP 409)                              |

## Konfiguration

| Variable                              | Zweck                                          |
| ------------------------------------- | ---------------------------------------------- |
| `MEDORA_LICENSE_API_URL`         | Adresse des Lizenzdienstes                     |
| `MEDORA_LICENSE_PUBLIC_KEY_FILE` | Datei mit dem öffentlichen Schlüssel (optional) |
| `MEDORA_LICENSE_PUBLIC_KEY`      | öffentlicher Schlüssel als Text (optional)     |

Ohne eigene Angabe wird der mitgelieferte Schlüssel verwendet. Administratoren können den Status prüfen und ein Token einspielen.

## Einrichtungsart aus der Lizenz

Die Einrichtungsart (Krankenhaus, Rettungsdienst, Leitstelle, Pflegeeinrichtung, Sonstige) und das Bundesland stammen normalerweise aus dem signierten Lizenztoken und lassen sich dann nicht überschreiben. Die Ersteinrichtung liest die Einrichtungsart aus dem Token und verlangt je nach Art weitere Angaben (Name der Hauptleitstelle bei der Leitstelle, Begriffe und Struktur bei „Sonstige“), siehe [Ersteinrichtung](../getting-started/first-setup.md). Das Eingabeformular wertet die Einrichtungsart nur zur Anzeige im Browser aus; der Server prüft das Token.
