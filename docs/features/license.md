# Lizenz

Für die Ersteinrichtung und den Betrieb ist ein gültiger Lizenzzugang erforderlich. Der API-Dienst prüft die Lizenz über den Lizenzdienst (`CLINICPULSE_LICENSE_API_URL`, HTTPS) und validiert signierte Tokens mit einem öffentlichen RSA-Schlüssel (mind. 2048 Bit).

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
| `CLINICPULSE_LICENSE_API_URL`         | Adresse des Lizenzdienstes                     |
| `CLINICPULSE_LICENSE_PUBLIC_KEY_FILE` | Datei mit dem öffentlichen Schlüssel (optional) |
| `CLINICPULSE_LICENSE_PUBLIC_KEY`      | öffentlicher Schlüssel als Text (optional)     |

Ohne eigene Angabe wird der mitgelieferte Schlüssel verwendet. Administratoren können den Status prüfen und ein Token einspielen.
