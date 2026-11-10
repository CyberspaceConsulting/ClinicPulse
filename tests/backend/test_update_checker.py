from io import BytesIO
import json
from urllib.request import Request

from app.update_checker import UpdateChecker


def test_check_detects_new_release_and_sends_optional_secret(tmp_path, monkeypatch):
    token_file = tmp_path / "github-token"
    token_file.write_text("test-readonly-token", encoding="utf-8")
    monkeypatch.setenv("CLINICPULSE_GITHUB_TOKEN_FILE", str(token_file))
    captured: list[Request] = []

    def fake_urlopen(request: Request, timeout: int):
        captured.append(request)
        assert timeout == 5
        return BytesIO(json.dumps([{
            "tag_name": "v0.2.0",
            "html_url": "https://github.com/CyberspaceConsulting/ClinicPulse/releases/tag/v0.2.0",
            "draft": False,
            "prerelease": False,
        }]).encode())

    monkeypatch.setattr("app.update_checker.urlopen", fake_urlopen)
    result = UpdateChecker().check()

    assert result["status"] == "update_available"
    assert result["current_version"] == "0.1.0"
    assert result["latest_version"] == "0.2.0"
    assert result["update_available"] is True
    assert captured[0].get_header("Authorization") == "Bearer test-readonly-token"


def test_update_check_does_not_require_secret_for_public_repo(monkeypatch):
    monkeypatch.delenv("CLINICPULSE_GITHUB_TOKEN_FILE", raising=False)
    captured: list[Request] = []

    def fake_urlopen(request: Request, timeout: int):
        captured.append(request)
        return BytesIO(json.dumps([{
            "tag_name": "0.1.0",
            "html_url": "https://github.com/CyberspaceConsulting/ClinicPulse/releases/tag/0.1.0",
            "draft": False,
            "prerelease": False,
        }]).encode())

    monkeypatch.setattr("app.update_checker.urlopen", fake_urlopen)
    result = UpdateChecker().check()

    assert result["status"] == "up_to_date"
    assert result["update_available"] is False
    assert captured[0].get_header("Authorization") is None


def test_nightly_channel_only_compares_nightly_releases(monkeypatch):
    monkeypatch.delenv("CLINICPULSE_GITHUB_TOKEN_FILE", raising=False)

    def fake_urlopen(request: Request, timeout: int):
        return BytesIO(json.dumps([
            {
                "tag_name": "v0.3.0",
                "html_url": "https://github.com/CyberspaceConsulting/ClinicPulse/releases/tag/v0.3.0",
                "draft": False,
                "prerelease": False,
            },
            {
                "tag_name": "v0.2.0-nightly.20261014",
                "html_url": "https://github.com/CyberspaceConsulting/ClinicPulse/releases/tag/v0.2.0-nightly.20261014",
                "draft": False,
                "prerelease": True,
            },
        ]).encode())

    monkeypatch.setattr("app.update_checker.urlopen", fake_urlopen)
    result = UpdateChecker().check(channel="nightly")
    assert result["channel"] == "nightly"
    assert result["latest_version"] == "0.2.0-nightly.20261014"
    assert result["update_available"] is True
