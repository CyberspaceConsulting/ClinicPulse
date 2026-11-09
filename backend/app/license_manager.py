import json
import os
import secrets
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .licensing import (
    AUDIENCE, FEDERAL_STATES, ISSUER, LICENSE_STATUSES, OPERATIONAL_PROFILES, LicenseConfigurationError, LicenseTokenError,
)

DEFAULT_API_URL = "https://lic.api.cyberspaceconsulting.de/api/v1"
LICENSE_STATUS_STATES = LICENSE_STATUSES | {"OVERDUE"}
STATUS_TOKEN_LIFETIME = timedelta(hours=48)
OFFLINE_GRACE = timedelta(days=7)
MAX_CLOCK_SKEW = timedelta(minutes=5)
RETRY_DELAYS = (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=6))


class LicenseServerUnavailable(Exception):
    pass


@dataclass(frozen=True)
class VerifiedStatus:
    token: str
    claims: dict[str, Any]


def _public_key() -> RSAPublicKey:
    key_path = os.environ.get("CLINICPULSE_LICENSE_PUBLIC_KEY_FILE")
    key_pem = os.environ.get("CLINICPULSE_LICENSE_PUBLIC_KEY")
    if key_path:
        try:
            key_pem = Path(key_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise LicenseConfigurationError("Configured license public key file cannot be read") from exc
    elif not key_pem:
        try:
            key_pem = Path(__file__).with_name("license_public.pem").read_text(encoding="utf-8")
        except OSError as exc:
            raise LicenseConfigurationError("Bundled license public key cannot be read") from exc
    if not key_pem:
        raise LicenseConfigurationError("CLINICPULSE_LICENSE_PUBLIC_KEY is not configured")
    try:
        key = serialization.load_pem_public_key(key_pem.encode())
    except (TypeError, ValueError) as exc:
        raise LicenseConfigurationError("Configured license public key is invalid") from exc
    if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
        raise LicenseConfigurationError("Configured license public key must be RSA with at least 2048 bits")
    return key


def _validate_institution_claims(claims: dict[str, Any]) -> None:
    institution_name = claims.get("institution_name")
    if institution_name is not None and (
        not isinstance(institution_name, str)
        or not institution_name.strip()
        or len(institution_name.strip()) > 120
    ):
        raise LicenseTokenError("License institution name is invalid")
    profile = claims.get("operational_profile")
    if profile is not None and profile not in OPERATIONAL_PROFILES:
        raise LicenseTokenError("License operational profile is invalid")
    federal_state = claims.get("federal_state")
    if federal_state is not None and federal_state not in FEDERAL_STATES:
        raise LicenseTokenError("License federal state is invalid")


def managed_federal_state(
    status: dict[str, Any] | None,
    license_claims: dict[str, Any] | None,
) -> str | None:
    for source in (status, license_claims):
        if source and source.get("federal_state"):
            return source["federal_state"]
    return None


def managed_institution(
    status: dict[str, Any] | None,
    license_claims: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Institution name and profile; the signed status (current) wins over the license token."""
    name = profile = None
    for source in (status, license_claims):
        if not source:
            continue
        name = name or source.get("institution_name")
        profile = profile or source.get("operational_profile")
    return name, profile


def _decode_license(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={
                "verify_exp": False,
                "require": ["exp", "iat", "iss", "aud", "sub", "jti", "license_status"],
            },
        )
    except jwt.InvalidTokenError as exc:
        raise LicenseTokenError("License signature or claims are invalid") from exc
    if (
        not isinstance(claims.get("sub"), str)
        or not claims["sub"].strip()
        or not isinstance(claims.get("jti"), str)
        or not claims["jti"].strip()
    ):
        raise LicenseTokenError("License identifiers are invalid")
    if claims.get("license_status") not in LICENSE_STATUSES:
        raise LicenseTokenError("License status is invalid")
    _validate_institution_claims(claims)
    if isinstance(claims.get("exp"), bool) or not isinstance(claims.get("exp"), (int, float)):
        raise LicenseTokenError("License expiry is invalid")
    if isinstance(claims.get("iat"), bool) or not isinstance(claims.get("iat"), (int, float)):
        raise LicenseTokenError("License issue time is invalid")
    max_users = claims.get("max_users")
    if max_users is not None and (
        isinstance(max_users, bool) or not isinstance(max_users, int) or max_users < 1
    ):
        raise LicenseTokenError("License user limit is invalid")
    features = claims.get("features")
    if features is not None and (
        not isinstance(features, list)
        or any(not isinstance(feature, str) or not feature for feature in features)
    ):
        raise LicenseTokenError("License feature list is invalid")
    return claims


def decode_license_claims(token: str) -> dict[str, Any]:
    return _decode_license(token)


def _post_json(path: str, payload: dict[str, str]) -> dict[str, Any]:
    base_url = os.environ.get("CLINICPULSE_LICENSE_API_URL", DEFAULT_API_URL).rstrip("/")
    if not base_url.startswith("https://"):
        raise LicenseConfigurationError("License Manager API must use HTTPS")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status != 200:
                raise LicenseServerUnavailable(f"License Manager returned HTTP {response.status}")
            response_data = response.read(64_001)
            if len(response_data) > 64_000:
                raise LicenseServerUnavailable("License Manager response exceeded size limit")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 409, 422}:
            raise LicenseTokenError(f"License Manager rejected request (HTTP {exc.code})") from exc
        raise LicenseServerUnavailable(f"License Manager returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LicenseServerUnavailable("License Manager could not be reached") from exc
    try:
        parsed = json.loads(response_data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LicenseServerUnavailable("License Manager returned invalid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("signed_status_token"), str):
        raise LicenseServerUnavailable("License Manager response has no signed status token")
    return parsed


def _verify_status(
    status_token: str,
    license_claims: dict[str, Any],
    installation_id: str,
    nonce: str,
) -> VerifiedStatus:
    try:
        claims = jwt.decode(
            status_token,
            _public_key(),
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["iss", "aud", "sub", "jti", "iat", "exp"]},
            leeway=MAX_CLOCK_SKEW,
        )
    except jwt.InvalidTokenError as exc:
        raise LicenseTokenError("Signed license status token is invalid or expired") from exc
    if claims.get("sub") != license_claims.get("sub"):
        raise LicenseTokenError("License status customer does not match")
    if claims.get("license_jti") != license_claims.get("jti"):
        raise LicenseTokenError("License status identifier does not match")
    if claims.get("installation_id") != installation_id or claims.get("nonce") != nonce:
        raise LicenseTokenError("License status is not bound to this installation request")
    if claims.get("license_status") not in LICENSE_STATUS_STATES:
        raise LicenseTokenError("License status is invalid")
    for field in ("license_expires_at", "checked_at"):
        value = claims.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LicenseTokenError(f"License status claim {field} is invalid")
    if (
        claims["iat"] > time.time() + MAX_CLOCK_SKEW.total_seconds()
        or claims["checked_at"] > time.time() + MAX_CLOCK_SKEW.total_seconds()
        or claims["license_expires_at"] != license_claims["exp"]
    ):
        raise LicenseTokenError("License status claims do not match the license")
    if claims["license_status"] == "GRACE_PERIOD":
        grace_until = claims.get("grace_until")
        if isinstance(grace_until, bool) or not isinstance(grace_until, (int, float)):
            raise LicenseTokenError("License grace-period end is invalid")
    if not isinstance(claims.get("vip"), bool) or not isinstance(claims.get("suppress_warnings"), bool):
        raise LicenseTokenError("License status flags are invalid")
    _validate_institution_claims(claims)
    return VerifiedStatus(status_token, claims)


def get_installation_id() -> str:
    return str(uuid.uuid4())


def activate_license(
    license_token: str,
    installation_id: str,
    version: str,
    release_channel: str,
) -> VerifiedStatus:
    license_claims = _decode_license(license_token)
    nonce = secrets.token_urlsafe(32)
    response = _post_json(
        "/instances/activate",
        {
            "license_token": license_token,
            "installation_id": installation_id,
            "clinicpulse_version": version,
            "release_channel": release_channel,
            "nonce": nonce,
        },
    )
    return _verify_status(response["signed_status_token"], license_claims, installation_id, nonce)


def check_license(
    license_token: str,
    installation_id: str,
    version: str,
    release_channel: str,
) -> VerifiedStatus:
    license_claims = _decode_license(license_token)
    nonce = secrets.token_urlsafe(32)
    response = _post_json(
        "/instances/check",
        {
            "license_token": license_token,
            "installation_id": installation_id,
            "clinicpulse_version": version,
            "release_channel": release_channel,
            "nonce": nonce,
        },
    )
    return _verify_status(response["signed_status_token"], license_claims, installation_id, nonce)


def check_retry_delay(failure_count: int) -> timedelta:
    index = max(0, min(failure_count - 1, len(RETRY_DELAYS) - 1))
    return RETRY_DELAYS[index]


def status_claims(
    token: str,
    license_token: str,
    installation_id: str,
) -> dict[str, Any]:
    try:
        license_claims = _decode_license(license_token)
        claims = jwt.decode(
            token,
            _public_key(),
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={
                "verify_exp": False,
                "require": [
                    "iss", "aud", "sub", "jti", "iat", "exp", "license_jti",
                    "installation_id", "nonce", "license_status", "license_expires_at",
                    "checked_at", "vip", "suppress_warnings",
                ],
            },
            leeway=MAX_CLOCK_SKEW,
        )
    except jwt.InvalidTokenError as exc:
        raise LicenseTokenError("Stored license status token is invalid") from exc
    if (
        claims.get("sub") != license_claims.get("sub")
        or claims.get("license_jti") != license_claims.get("jti")
        or claims.get("installation_id") != installation_id
        or not isinstance(claims.get("nonce"), str)
        or not claims["nonce"]
        or claims.get("license_status") not in LICENSE_STATUS_STATES
    ):
        raise LicenseTokenError("Stored license status is not bound to this installation")
    for field in ("iat", "exp", "license_expires_at", "checked_at"):
        value = claims.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise LicenseTokenError(f"Stored license status claim {field} is invalid")
    if (
        not isinstance(claims.get("vip"), bool)
        or not isinstance(claims.get("suppress_warnings"), bool)
        or claims["iat"] > time.time() + MAX_CLOCK_SKEW.total_seconds()
        or claims["checked_at"] > time.time() + MAX_CLOCK_SKEW.total_seconds()
        or claims["exp"] <= claims["checked_at"]
        or claims["license_expires_at"] != license_claims["exp"]
    ):
        raise LicenseTokenError("Stored license status claims do not match the license")
    if claims["license_status"] == "GRACE_PERIOD":
        grace_until = claims.get("grace_until")
        if isinstance(grace_until, bool) or not isinstance(grace_until, (int, float)):
            raise LicenseTokenError("Stored license grace-period end is invalid")
    _validate_institution_claims(claims)
    return claims


def license_is_read_only(
    token: str | None,
    last_successful_check_at: datetime | None,
    now: datetime | None = None,
    license_token: str | None = None,
    installation_id: str | None = None,
) -> tuple[bool, str | None]:
    if not token or last_successful_check_at is None or not license_token or not installation_id:
        return True, "License has not been activated or checked"
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    checked_at = last_successful_check_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    try:
        claims = status_claims(token, license_token, installation_id)
    except (LicenseConfigurationError, LicenseTokenError):
        return True, "Stored license status could not be verified"
    signed_checked_at = datetime.fromtimestamp(claims["checked_at"], timezone.utc)
    checked_at = min(checked_at, signed_checked_at)
    state = claims.get("license_status")
    if state == "BLOCKED":
        return True, "License is blocked"
    if state == "OVERDUE":
        return True, "License is overdue"
    if state == "GRACE_PERIOD":
        grace_until = claims.get("grace_until")
        if isinstance(grace_until, (int, float)) and current.timestamp() >= grace_until:
            return True, "License grace period has expired"
    if current - checked_at >= OFFLINE_GRACE:
        return True, "License Manager has been unreachable for more than seven days"
    return False, None
