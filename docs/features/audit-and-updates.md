# Protokoll und Updates

## Änderungsprotokoll

Änderungen an Konten, Abteilungen, Mitarbeitenden, Schichttypen, Zuweisungen, Abwesenheiten, Archiven, Einstellungen und Backup-Konfiguration werden automatisch protokolliert. Administratoren können das Protokoll abrufen.

## Update-Hinweise

ClinicPulse fragt alle 6 Stunden die öffentlichen Docker-Pakete in der GitHub Container Registry ab. Ein Update wird nur angeboten, wenn sowohl das Backend- als auch das Web-Image mit demselben Versions-Tag vorhanden sind. `main` umfasst endgültige Versionen, `test` die Vorabversionen mit `-alpha` oder `-test`. Diese Kanäle sind keine Git-Branches. Bestehende Einstellungen `stable` und `nightly` werden zu `main` beziehungsweise `test` migriert.

Die installierte Version wird beim Release-Build im Backend-Image hinterlegt. Bei älteren Images und Builds aus dem Quellcode wird ersatzweise `CLINICPULSE_VERSION` verwendet. Alte Release-Compose-Dateien mit Werten wie `-0.2.1-alpha` werden als `v-0.2.1-alpha` erkannt. Neu installierte Alpha-/Test-Images wählen standardmäßig `test`; ein bereits gespeicherter Kanal bleibt erhalten. Schlägt die Registry-Abfrage fehl, wird der Fehler 5 Minuten zwischengespeichert. Der Hinweis installiert keine Updates automatisch; Image-Tags garantieren für sich genommen noch kein veröffentlichtes Release mit Compose-Datei.

Die manuellen Schritte stehen in der [Docker-Update-Anleitung](../getting-started/update.md).
