from datetime import datetime, timedelta, timezone
import json
import os
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_configured_version = os.environ.get("CLINICPULSE_IMAGE_VERSION") or os.environ.get("CLINICPULSE_VERSION", "0.1.0")
APP_VERSION = f"v{_configured_version}" if _configured_version.startswith("-") else _configured_version
REPOSITORY_URL = "https://github.com/CyberspaceConsulting/ClinicPulse"
PACKAGE_URL = "https://github.com/orgs/CyberspaceConsulting/packages/container/package/clinicpulse-backend"
REGISTRY_URL = "https://ghcr.io"
IMAGE_NAMES = ("cyberspaceconsulting/clinicpulse-backend", "cyberspaceconsulting/clinicpulse-web")
CHECK_INTERVAL = timedelta(hours=6)
ERROR_CACHE_INTERVAL = timedelta(minutes=5)
VERSION_PATTERN = re.compile(
    r"^(?:v-?|)(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*))?$"
)


class RegistryResponseError(ValueError):
    pass


def default_update_channel() -> str:
    match = VERSION_PATTERN.fullmatch(APP_VERSION)
    if match and match.group(4) and match.group(4).split(".")[0].split("-")[0].casefold() in {"alpha", "test"}:
        return "test"
    return "main"


class UpdateChecker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cached_result: dict[str, object] | None = None
        self._cache_expires_at = datetime.min.replace(tzinfo=timezone.utc)

    def check(self, channel: str = "main", force: bool = False) -> dict[str, object]:
        if channel not in {"main", "test"}:
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
        current_match = VERSION_PATTERN.fullmatch(APP_VERSION)
        if not current_match:
            return self._result(
                "unavailable",
                message="Die installierte Image-Version ist unbekannt oder ungültig.",
                channel=channel,
            )
        try:
            backend_tags = self._image_tags(IMAGE_NAMES[0])
            web_tags = self._image_tags(IMAGE_NAMES[1])
        except HTTPError as exc:
            if exc.code in {401, 403, 429}:
                message = "Die GitHub-Container-Registry hat die Update-Abfrage begrenzt oder verweigert."
            else:
                message = f"Container-Registry-Update-Abfrage fehlgeschlagen (HTTP {exc.code})."
            return self._result("unavailable", message=message, channel=channel)
        except (URLError, TimeoutError, OSError):
            return self._result(
                "unavailable", message="Die GitHub-Container-Registry ist für die Update-Prüfung nicht erreichbar.", channel=channel
            )
        except (json.JSONDecodeError, UnicodeDecodeError, RegistryResponseError):
            return self._result(
                "unavailable", message="Die GitHub-Container-Registry hat eine ungültige Antwort geliefert.", channel=channel
            )

        candidates: list[tuple[tuple[object, ...], str]] = []
        for tag in backend_tags & web_tags:
            match = VERSION_PATTERN.fullmatch(tag)
            if match is None:
                continue
            prerelease = match.group(4)
            if channel == "main" and prerelease is not None:
                continue
            if channel == "test" and (prerelease is None or prerelease.split(".")[0].split("-")[0].casefold() not in {"alpha", "test"}):
                continue
            candidates.append((self._version_tuple(match), tag))
        if not candidates:
            return self._result("no_release", message=f"Kein Docker-Image-Paar für den {channel}-Kanal gefunden.", channel=channel)
        latest_tuple, latest_version = max(candidates)
        update_available = latest_tuple > self._version_tuple(current_match)
        return self._result(
            "update_available" if update_available else "up_to_date",
            channel=channel,
            latest_version=latest_version,
            release_url=PACKAGE_URL,
            update_available=update_available,
            message=f"Version {latest_version} ist verfügbar." if update_available else "ClinicPulse ist auf dem aktuellen Release-Stand.",
        )

    @staticmethod
    def _image_tags(image: str) -> set[str]:
        query = urlencode({"service": "ghcr.io", "scope": f"repository:{image}:pull"})
        with urlopen(Request(f"{REGISTRY_URL}/token?{query}"), timeout=5) as response:
            token_data = json.loads(response.read())
        if not isinstance(token_data, dict) or not isinstance(token_data.get("token"), str) or not token_data["token"]:
            raise RegistryResponseError("Invalid registry token response")
        token = token_data["token"]
        tags: set[str] = set()
        last: str | None = None
        while True:
            params = {"n": "100"}
            if last is not None:
                params["last"] = last
            request = Request(
                f"{REGISTRY_URL}/v2/{image}/tags/list?{urlencode(params)}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlopen(request, timeout=5) as response:
                data = json.loads(response.read())
                link = response.headers.get("Link")
            if not isinstance(data, dict) or not isinstance(data.get("tags"), list) or not all(isinstance(tag, str) for tag in data["tags"]):
                raise RegistryResponseError("Invalid registry tag response")
            page = data["tags"]
            tags.update(page)
            if not link:
                return tags
            if not page or page[-1] == last:
                raise RegistryResponseError("Invalid registry pagination")
            last = page[-1]

    @staticmethod
    def _version_tuple(match: re.Match[str]) -> tuple[object, ...]:
        major, minor, patch, prerelease = match.groups()
        if prerelease is None:
            prerelease_parts: tuple[tuple[int, object], ...] = ((2, 0),)
        else:
            prerelease_parts = tuple(
                (0, int(part)) if part.isdigit() else (1, part.casefold())
                for part in re.split(r"[.-]", prerelease)
            )
        return int(major), int(minor), int(patch), prerelease_parts

    @staticmethod
    def _result(
        result_status: str,
        *,
        message: str,
        channel: str = "main",
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
