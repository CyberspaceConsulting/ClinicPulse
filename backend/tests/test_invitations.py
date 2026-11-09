import smtplib

import pytest

from app import invitations


def test_invitation_uses_starttls_and_sends_one_time_link(monkeypatch, tmp_path):
    password_file = tmp_path / "smtp_password"
    password_file.write_text("test-smtp-password", encoding="utf-8")
    monkeypatch.setenv("CLINICPULSE_SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("CLINICPULSE_PUBLIC_URL", "https://clinic.example.test")
    monkeypatch.setenv("CLINICPULSE_SMTP_USERNAME", "clinicpulse")
    monkeypatch.setenv("CLINICPULSE_SMTP_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("CLINICPULSE_SMTP_FROM", "clinicpulse@example.test")
    monkeypatch.setenv("CLINICPULSE_SMTP_USE_SSL", "false")
    monkeypatch.setenv("CLINICPULSE_SMTP_USE_STARTTLS", "true")
    sent_messages = []
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def starttls(self):
            events.append(("starttls",))

        def login(self, username, password):
            events.append(("login", username, password))

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    invitations.send_invitation("staff@example.test", "staff-user", "one-time-token")

    assert events == [
        ("connect", "mail.example.test", 587, 15),
        ("starttls",),
        ("login", "clinicpulse", "test-smtp-password"),
    ]
    assert sent_messages[0]["To"] == "staff@example.test"
    assert "one-time-token" in sent_messages[0].get_content()
    assert "https://clinic.example.test/#invite=one-time-token" in sent_messages[0].get_content()


def test_invitation_rejects_non_https_public_urls(monkeypatch):
    monkeypatch.setenv("CLINICPULSE_SMTP_HOST", "mail.example.test")
    monkeypatch.setenv("CLINICPULSE_PUBLIC_URL", "http://clinic.example.test")

    with pytest.raises(RuntimeError, match="Public instance URL"):
        invitations.send_invitation("staff@example.test", "staff-user", "one-time-token")


def test_test_email_sends_using_saved_mail_configuration(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def starttls(self):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    configuration = invitations.MailConfiguration(
        public_url="https://clinic.example.test",
        smtp_host="mail.example.test",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        from_address="clinicpulse@example.test",
        use_ssl=False,
        use_starttls=True,
    )
    invitations.send_test_email("admin@example.test", configuration)

    assert sent_messages[0]["To"] == "admin@example.test"
    assert "erfolgreich konfiguriert" in sent_messages[0].get_content()
