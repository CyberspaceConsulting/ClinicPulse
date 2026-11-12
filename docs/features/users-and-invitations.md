# Benutzer und Einladungen

## Konten

- Benutzernamen sind eindeutig („Username is already in use“).
- Konten können gesperrt und entsperrt werden. Ein eingeladenes Konto muss zuerst die Einladung annehmen, bevor es entsperrt werden kann.
- Die Anzahl aktiver Konten ist durch die [Lizenz](license.md) begrenzt („Licensed user limit reached“).

## Wer darf wen anlegen?

| Aktion                                      | Berechtigt |
| ------------------------------------------- | ---------- |
| Krankenhausleitung anlegen und verwalten    | nur Administrator |
| Administratorkonten anlegen und verwalten   | nur Administrator |
| Personaler-Rolle vergeben                   | Leitung |
| Mitarbeiterkonten anlegen und verwalten     | Personaler sowie Leitung oder Stellvertretung der betreffenden Abteilung |

Eine Abteilungsleitung oder Stellvertretung darf nur Mitarbeiterkonten für die eigene Abteilung verwalten. Die Person muss in der Abteilung eingetragen sein und eine dort als leitungsberechtigt markierte Qualifikation haben. Die Systemrolle „Oberarzt“ allein verleiht keine Kontoverwaltungsrechte. Die getrennte Mitarbeiterverwaltung weist einer Person eine Hauptabteilung, weitere Abteilungen und abteilungsspezifische Qualifikationen zu. Ein Mitarbeiterkonto kann mit einer Person verknüpft werden, die mindestens einer der Abteilungen des Kontos angehört; das Konto einer Person mit der Rolle „Mitarbeiter“ erhält beim Anlegen oder Bearbeiten der Person Zugriff auf alle ihre Abteilungen.

## Einladungen

Statt eines Passworts kann ein Konto per E-Mail eingeladen werden. Dafür müssen [E-Mail](mail.md) und die öffentliche HTTPS-Adresse konfiguriert sein.

- Ohne Passwort ist eine Einladungs-E-Mail-Adresse erforderlich.
- Eine Einladung kann erneut gesendet oder widerrufen werden.
- Abgelaufene oder ungültige Einladungen werden abgelehnt („Invitation is invalid or expired“).

## Konto ohne E-Mail

Deaktiviert der Administrator den [E-Mail-Versand](mail.md), können Leitung und Personalverwaltung Konten ohne SMTP und ohne E-Mail-Adresse anlegen. Stattdessen wird ein Startpasswort vergeben und über einen sicheren Kanal an die Person übermittelt. Bei der ersten Anmeldung muss sie ein anderes Passwort setzen; bis dahin sind andere geschützte Funktionen und API-Zugriffe gesperrt. Dies gilt auch für Konten, die zusammen mit Mitarbeitenden angelegt werden.

Bereits eingeladene, noch nicht aktivierte Konten können bei deaktiviertem Versand durch Bearbeiten und Vergabe eines Startpassworts aktiviert werden. Ihr bisheriger Einladungslink wird dabei widerrufen. Auch ein später durch die Verwaltung neu gesetztes Passwort muss beim nächsten Login geändert werden, solange der Versand deaktiviert ist.
