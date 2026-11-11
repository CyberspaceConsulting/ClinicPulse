from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from app import update_checker
from app.update_checker import UpdateChecker


class RegistryResponse(BytesIO):
    def __init__(self, value, link=None):
        super().__init__(json.dumps(value).encode())
        self.headers = {"Link": link} if link else {}


def mock_registry(monkeypatch, backend_tags, web_tags, page_size=None):
    calls = []

    def fake_urlopen(request, timeout):
        assert timeout == 5
        url = urlsplit(request.full_url)
        assert url.netloc == "ghcr.io"
        calls.append(request)
        if url.path == "/token":
            return RegistryResponse({"token": "public-registry-token"})
        assert request.get_header("Authorization") == "Bearer public-registry-token"
        tags = backend_tags if "clinicpulse-backend" in url.path else web_tags
        params = parse_qs(url.query)
        last = params.get("last", [None])[0]
        start = tags.index(last) + 1 if last is not None else 0
        page = tags[start:start + page_size] if page_size else tags[start:]
        link = '<next>; rel="next"' if page_size and start + page_size < len(tags) else None
        return RegistryResponse({"tags": page}, link)

    monkeypatch.setattr(update_checker, "urlopen", fake_urlopen)
    return calls


def test_registry_checks_both_images_and_pagination(monkeypatch):
    monkeypatch.setattr(update_checker, "APP_VERSION", "v-0.2.1-alpha")
    calls = mock_registry(monkeypatch, [
        "v-0.2.1-alpha", "v-0.2.2-alpha", "v-0.2.3-alpha",
    ], ["v-0.2.1-alpha", "v-0.2.2-alpha"], page_size=1)
    checker = UpdateChecker()
    result = checker.check("test")
    assert result["current_version"] == "v-0.2.1-alpha"
    assert result["latest_version"] == "v-0.2.2-alpha"
    assert result["update_available"] is True
    assert result["release_url"] == update_checker.PACKAGE_URL
    assert len(calls) == 7
    assert checker.check("test") == result
    assert len(calls) == 7
    assert checker.check("main")["status"] == "no_release"


@pytest.mark.parametrize(("channel", "expected"), [
    ("main", "v-1.0.0"), ("test", "v-1.1.0-test.2"),
])
def test_channels_filter_and_sort_real_tags(monkeypatch, channel, expected):
    monkeypatch.setattr(update_checker, "APP_VERSION", "v-0.2.1-alpha")
    tags = [
        "v-0.2.2-alpha", "v-1.0.0", "v-1.1.0-alpha", "v-1.1.0-test.2",
        "v-1.1.0-test.1", "v-3.0.0-nightly", "latest",
    ]
    mock_registry(monkeypatch, tags, tags)
    assert UpdateChecker().check(channel)["latest_version"] == expected


@pytest.mark.parametrize(("installed", "available", "update"), [
    ("v-0.2.1-alpha", "v-0.2.1-alpha", False),
    ("v-0.2.1-alpha", "v-0.2.2-alpha", True),
    ("0.2.1-alpha", "v-0.2.2-alpha", True),
    ("v-1.0.0", "v-1.0.0-alpha", False),
    ("v-1.0.0-test.2", "v-1.0.0-test.10", True),
    ("v-1.0.0-alpha", "v-1.0.0-alpha.1", True),
])
def test_version_order(monkeypatch, installed, available, update):
    monkeypatch.setattr(update_checker, "APP_VERSION", installed)
    mock_registry(monkeypatch, [available], [available])
    assert UpdateChecker().check("test")["update_available"] is update


def test_missing_image_pair_and_invalid_installed_version(monkeypatch):
    monkeypatch.setattr(update_checker, "APP_VERSION", "v-0.2.1-alpha")
    mock_registry(monkeypatch, ["v-0.2.2-alpha"], [])
    assert UpdateChecker().check("test")["status"] == "no_release"
    monkeypatch.setattr(update_checker, "APP_VERSION", "unknown")
    result = UpdateChecker().check("test")
    assert result["status"] == "unavailable"
    assert result["channel"] == "test"
    assert "installierte Image-Version" in result["message"]


@pytest.mark.parametrize("error", [
    URLError("unreachable"),
    HTTPError("https://ghcr.io", 403, "forbidden", {}, None),
    HTTPError("https://ghcr.io", 500, "server error", {}, None),
])
def test_registry_errors_are_not_reported_as_success(monkeypatch, error):
    def fail(request, timeout):
        raise error
    monkeypatch.setattr(update_checker, "urlopen", fail)
    result = UpdateChecker().check("test")
    assert result["status"] == "unavailable"
    assert result["channel"] == "test"
    assert result["update_available"] is False


def test_invalid_registry_response(monkeypatch):
    monkeypatch.setattr(update_checker, "urlopen", lambda *args, **kwargs: RegistryResponse({"token": None}))
    assert UpdateChecker().check("main")["status"] == "unavailable"


def test_version_from_image_takes_precedence_over_legacy_compose():
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(Path(__file__).resolve().parents[2] / "backend"), "CLINICPULSE_VERSION": "-0.2.1-alpha"})
    env.pop("CLINICPULSE_IMAGE_VERSION", None)
    command = [sys.executable, "-c", "from app.update_checker import APP_VERSION, default_update_channel; print(APP_VERSION, default_update_channel())"]
    assert subprocess.check_output(command, env=env, text=True).strip() == "v-0.2.1-alpha test"
    env["CLINICPULSE_IMAGE_VERSION"] = "v-0.2.2-alpha"
    assert subprocess.check_output(command, env=env, text=True).strip() == "v-0.2.2-alpha test"
