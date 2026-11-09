# E-Mail

E-Mail wird für Einladungen benötigt und ist optional. Die Einstellungen lassen sich per Umgebungsvariable (siehe [Umgebungsvariablen](../getting-started/environment-variables.md)) vorgeben und vom Administrator in der Anwendung ändern, inklusive Testversand.

## Einstellungen

| Feld                 | Hinweis                                                      |
| -------------------- | ------------------------------------------------------------ |
| Öffentliche URL      | muss HTTPS sein (Ausnahme: `localhost`, `127.0.0.1`, `::1`)  |
| SMTP-Host und -Port  | Port 1–65535, Standard 587                                   |
| Benutzer und Passwort | Passwort wird nie zurückgegeben; Löschen ist separat möglich |
| Absenderadresse      | Pflichtfeld                                                  |
| Implizites TLS / STARTTLS | nicht gleichzeitig aktivierbar                          |

Mit SMTP-Zugangsdaten muss TLS aktiv sein. Schlägt der Versand fehl, erhält die Einladung den Status `delivery_failed` und kann erneut gesendet werden.
