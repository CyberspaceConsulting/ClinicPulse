from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_VERSION = os.environ.get("CLINICPULSE_VERSION", "0.1.0")
REPOSITORY_URL = "https://github.com/the1andoni/ClinicPulse"
RELEASES_API_URL = "https://api.github.com/repos/the1andoni/ClinicPulse/releases?per_page=30"
CHECK_INTERVAL = timedelta(hours=6)
ERROR_CACHE_INTERVAL = timedelta(minutes=5)
VERSION_PATTERN = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$"
)


class UpdateChecker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached_result: dict[str, object] | None = None
        self._cache_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    def check(self, channel: str = "stable", force: bool = False) -> dict[str, object]:
        if channel not in {"stable", "nightly"}:
            raise ValueError("Unsupported release channel")
        with self._lock:
            now = datetime.now(timezone.utc)
            if (
                not force
                and self._cached_result is not None
                and self._cached_result.get("channel") == channel
                and now < self._cache_expires_at
            ):
                return dict(self._cached_result)
            result = self._fetch_latest_release(channel)
            self._cached_result = result
            cache_duration = CHECK_INTERVAL if result["status"] in {"up_to_date", "update_available", "no_release"} else ERROR_CACHE_INTERVAL
            self._cache_expires_at = now + cache_duration
            return dict(result)

    def _fetch_latest_release(self, channel: str) -> dict[str, object]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ClinicPulse/{APP_VERSION}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token_file = os.environ.get("CLINICPULSE_GITHUB_TOKEN_FILE")
        if token_file:
            try:
                token = Path(token_file).read_text(encoding="utf-8").strip()
            except OSError:
                return self._result("unavailable", message="Der optionale GitHub-Zugriffsschlüssel ist nicht lesbar.")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        request = Request(RELEASES_API_URL, headers=headers)
        try:
            with urlopen(request, timeout=5) as response:
                release_data = json.loads(response.read())
        except HTTPError as exc:
            if exc.code == 404:
                return self._result(
                    "no_release",
                    message="Kein öffentlich erreichbares GitHub-Release gefunden.",
                    channel=channel,
                )
            if exc.code == 403 or exc.code == 429:
                return self._result(
                    "unavailable",
                    message="GitHub hat die Update-Abfrage begrenzt oder verweigert.",
                    channel=channel,
                )
            return self._result(
                "unavailable",
                message=f"GitHub-Update-Abfrage fehlgeschlagen (HTTP {exc.code}).",
                channel=channel,
            )
        except (URLError, TimeoutError, OSError):
            return self._result(
                "unavailable",
                message="GitHub ist für die Update-Prüfung nicht erreichbar.",
                channel=channel,
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._result(
                "unavailable",
                message="GitHub hat eine ungültige Antwort geliefert.",
                channel=channel,
            )

        if not isinstance(release_data, list):
            return self._result(
                "unavailable",
                message="GitHub hat eine ungültige Release-Antwort geliefert.",
                channel=channel,
            )
        current_match = VERSION_PATTERN.fullmatch(APP_VERSION)
        if not current_match:
            return self._result(
                "unavailable",
                message="Release-Versionen müssen dem Format vX.Y.Z entsprechen.",
                channel=channel,
            )
        current_version = self._version_tuple(current_match)
        releases = []
        for release in release_data:
            if not isinstance(release, dict) or release.get("draft") is True:
                continue
            is_prerelease = release.get("prerelease") is True
            tag_name = release.get("tag_name")
            release_url = release.get("html_url")
            if not isinstance(tag_name, str) or not isinstance(release_url, str):
                continue
            match = VERSION_PATTERN.fullmatch(tag_name)
            if match is None:
                continue
            prerelease_label = match.group(4)
            is_nightly = is_prerelease and prerelease_label is not None and "nightly" in prerelease_label.casefold()
            if channel == "stable" and (is_prerelease or prerelease_label is not None):
                continue
            if channel == "nightly" and not is_nightly:
                continue
            version = self._version_tuple(match)
            releases.append((version, tag_name.removeprefix("v"), release_url))
        if not releases:
            return self._result(
                "no_release",
                message=f"Kein veröffentlichtes Release für den {channel}-Kanal gefunden.",
                channel=channel,
            )
        latest_tuple, latest_version, release_url = max(releases, key=lambda release: release[0])
        update_available = latest_tuple > current_version
        return self._result(
            "update_available" if update_available else "up_to_date",
            channel=channel,
            latest_version=latest_version,
            release_url=release_url,
            update_available=update_available,
            message=(
                f"Version {latest_version} ist verfügbar."
                if update_available else "ClinicPulse ist auf dem aktuellen Release-Stand."
            ),
        )

    @staticmethod
    def _version_tuple(match: re.Match[str]) -> tuple[object, ...]:
        major, minor, patch, prerelease = match.groups()
        prerelease_parts: tuple[tuple[int, object], ...]
        if prerelease is None:
            prerelease_parts = ((1, 0),)
        else:
            prerelease_parts = tuple(
                (0, int(part)) if part.isdigit() else (1, part.casefold())
                for part in prerelease.split(".")
            ) + ((0, -1),)
        return int(major), int(minor), int(patch), prerelease_parts

    @staticmethod
    def _result(
        result_status: str,
        *,
        message: str,
        channel: str = "stable",
        latest_version: str | None = None,
        release_url: str | None = None,
        update_available: bool = False,
    ) -> dict[str, object]:
        return {
            "current_version": APP_VERSION,
            "channel": channel,
            "latest_version": latest_version,
            "update_available": update_available,
            "status": result_status,
            "message": message,
            "release_url": release_url,
            "repository_url": REPOSITORY_URL,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


update_checker = UpdateChecker()
