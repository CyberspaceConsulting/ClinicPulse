import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode, urlsplit


@dataclass(frozen=True)
class MailConfiguration:
    public_url: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    from_address: str
    use_ssl: bool
    use_starttls: bool


def environment_mail_configuration() -> MailConfiguration:
    password_file = os.environ.get("MEDORA_SMTP_PASSWORD_FILE")
    password = ""
    if password_file:
        try:
            password = Path(password_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError("Configured SMTP password file cannot be read") from exc
    return MailConfiguration(
        public_url=os.environ.get("MEDORA_PUBLIC_URL", "").strip().rstrip("/"),
        smtp_host=os.environ.get("MEDORA_SMTP_HOST", "").strip(),
        smtp_port=int(os.environ.get("MEDORA_SMTP_PORT", "587")),
        smtp_username=os.environ.get("MEDORA_SMTP_USERNAME", ""),
        smtp_password=password,
        from_address=os.environ.get("MEDORA_SMTP_FROM", "").strip(),
        use_ssl=os.environ.get("MEDORA_SMTP_USE_SSL", "false").casefold() == "true",
        use_starttls=os.environ.get("MEDORA_SMTP_USE_STARTTLS", "true").casefold() == "true",
    )


def _validate(configuration: MailConfiguration) -> None:
    if not configuration.smtp_host or not configuration.public_url:
        raise RuntimeError("Email delivery requires SMTP host and public instance URL")
    parsed_url = urlsplit(configuration.public_url.rstrip("/"))
    local_http_hosts = {"localhost", "127.0.0.1", "::1"}
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.netloc
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
        or (parsed_url.scheme != "https" and parsed_url.hostname not in local_http_hosts)
    ):
        raise RuntimeError("Public instance URL must use HTTPS")
    if not configuration.from_address:
        raise RuntimeError("SMTP sender address is not configured")
    if configuration.smtp_username and not configuration.smtp_password:
        raise RuntimeError("SMTP password is required when SMTP username is configured")
    if configuration.smtp_username and not (configuration.use_ssl or configuration.use_starttls):
        raise RuntimeError("SMTP authentication requires TLS")


def _send(message: EmailMessage, configuration: MailConfiguration) -> None:
    _validate(configuration)
    smtp_class = smtplib.SMTP_SSL if configuration.use_ssl else smtplib.SMTP
    with smtp_class(configuration.smtp_host, configuration.smtp_port, timeout=15) as smtp:
        if not configuration.use_ssl and configuration.use_starttls:
            smtp.starttls()
        if configuration.smtp_username:
            smtp.login(configuration.smtp_username, configuration.smtp_password)
        smtp.send_message(message)


def send_invitation(
    recipient: str,
    username: str,
    token: str,
    configuration: MailConfiguration | None = None,
) -> None:
    configuration = configuration or environment_mail_configuration()
    _validate(configuration)
    invite_url = f"{configuration.public_url.rstrip('/')}/#{urlencode({'invite': token})}"
    message = EmailMessage()
    message["Subject"] = "Dein Zugang zu Medora"
    message["From"] = configuration.from_address
    message["To"] = recipient
    message.set_content(
        f"Hallo,\n\n"
        f"für dich wurde ein Medora-Zugang mit dem Benutzernamen „{username}“ angelegt.\n"
        f"Öffne innerhalb von 24 Stunden den folgenden Einmal-Link und lege dein eigenes Passwort fest:\n\n"
        f"{invite_url}\n\n"
        "Der Link ist nur einmal verwendbar. Falls du diese Einladung nicht erwartet hast, "
        "kannst du diese E-Mail ignorieren.\n"
    )
    _send(message, configuration)


def send_test_email(recipient: str, configuration: MailConfiguration) -> None:
    message = EmailMessage()
    message["Subject"] = "Medora – Test der E-Mail-Konfiguration"
    message["From"] = configuration.from_address
    message["To"] = recipient
    message.set_content(
        "Der E-Mail-Versand für diese Medora-Instanz ist erfolgreich konfiguriert.\n"
    )
    _send(message, configuration)
