# Installation

Voraussetzungen: Docker Engine, Docker Compose v2 und OpenSSL.

## Aus dem Quellcode

```sh
git clone https://github.com/the1andoni/ClinicPulse.git
cd ClinicPulse

mkdir -p secrets
chmod 700 secrets
umask 077
if [ ! -f secrets/data_encryption_key ]; then
  openssl rand -base64 48 > secrets/data_encryption_key
fi
touch secrets/smtp_password
chmod 600 secrets/data_encryption_key secrets/smtp_password

docker compose up --build -d
```

Rufe anschließend <http://localhost:8080> auf (Port über `CLINICPULSE_PORT` änderbar).

Für die Ersteinrichtung ist ein gültiger Lizenzzugang erforderlich. Der API-Dienst benötigt ausgehenden HTTPS-Zugriff auf den Lizenzdienst, dessen Adresse über `CLINICPULSE_LICENSE_API_URL` festgelegt wird.

## Nützliche Befehle

```sh
docker compose logs -f
docker compose down
```

## Wichtige Hinweise

- Die Datenbank liegt im Docker-Volume `clinicpulse_data`.
- **Sichere `secrets/data_encryption_key` getrennt und geschützt.** Ohne diesen Schlüssel können verschlüsselte Daten nicht mehr gelesen werden.
- SMTP ist optional. Für Einladungs-E-Mails müssen SMTP und die öffentliche HTTPS-Adresse der Instanz konfiguriert sein, siehe [Konfiguration](configuration.md).
- Installationsartefakte stehen unter [GitHub Releases](https://github.com/the1andoni/ClinicPulse/releases).
