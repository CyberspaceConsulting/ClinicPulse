# Benutzer und Einladungen

## Konten

- Benutzernamen sind eindeutig („Username is already in use“).
- Konten können gesperrt und entsperrt werden. Ein eingeladenes Konto muss zuerst die Einladung annehmen, bevor es entsperrt werden kann.
- Die Anzahl aktiver Konten ist durch die [Lizenz](license.md) begrenzt („Licensed user limit reached“).

## Wer darf wen anlegen?

| Aktion                                    | Berechtigt                          |
| ----------------------------------------- | ----------------------------------- |
| Krankenhausleitung anlegen und verwalten  | nur Administrator                   |
| Personaler-Rolle vergeben                 | nur Leitung                         |
| Konten für Mitarbeitende anlegen/verwalten | Personaler (ausschließlich Mitarbeiter-Konten) und Leitung |

## Einladungen

Statt eines Passworts kann ein Konto per E-Mail eingeladen werden. Dafür müssen [E-Mail](mail.md) und die öffentliche HTTPS-Adresse konfiguriert sein.

- Ohne Passwort ist eine Einladungs-E-Mail-Adresse erforderlich.
- Eine Einladung kann erneut gesendet oder widerrufen werden.
- Abgelaufene oder ungültige Einladungen werden abgelehnt („Invitation is invalid or expired“).
