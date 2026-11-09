import argparse
from datetime import datetime, timezone
import getpass
import os
from pathlib import Path
import sys
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "clinicpulse-licensing"
AUDIENCE = "clinicpulse"
LICENSE_STATUSES = {"PAID", "GRACE_PERIOD", "BLOCKED"}
OPERATIONAL_PROFILES = {"hospital", "rescue_service", "ils", "care_facility", "other"}
FEDERAL_STATES = {
    "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen",
    "Mecklenburg-Vorpommern", "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz",
    "Saarland", "Sachsen", "Sachsen-Anhalt", "Schleswig-Holstein", "Thüringen",
}


class LicenseConfigurationError(Exception):
    pass


class LicenseTokenError(Exception):
    pass


def validate_license_token(token: str) -> dict[str, object]:
    public_key_file = os.environ.get("CLINICPULSE_LICENSE_PUBLIC_KEY_FILE")
    public_key = os.environ.get("CLINICPULSE_LICENSE_PUBLIC_KEY")
    if public_key_file:
        try:
            public_key = Path(public_key_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise LicenseConfigurationError("Configured license public key file cannot be read") from exc
    elif not public_key:
        try:
            public_key = Path(__file__).with_name("license_public.pem").read_text(encoding="utf-8")
        except OSError as exc:
            raise LicenseConfigurationError("Bundled license public key cannot be read") from exc
    if not public_key:
        raise LicenseConfigurationError("CLINICPULSE_LICENSE_PUBLIC_KEY is not configured")
    try:
        parsed_public_key = serialization.load_pem_public_key(public_key.encode())
    except (TypeError, ValueError) as exc:
        raise LicenseConfigurationError("Configured license public key is invalid") from exc
    if not isinstance(parsed_public_key, rsa.RSAPublicKey) or parsed_public_key.key_size < 2048:
        raise LicenseConfigurationError("Configured license public key must be RSA with at least 2048 bits")
    try:
        claims = jwt.decode(
            token,
            parsed_public_key,
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "license_status"]},
        )
    except jwt.InvalidTokenError as exc:
        raise LicenseTokenError("License signature or claims are invalid") from exc
    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise LicenseTokenError("License customer identifier is invalid")
    license_status = claims.get("license_status")
    if not isinstance(license_status, str) or license_status not in LICENSE_STATUSES:
        raise LicenseTokenError("License status is invalid")
    if license_status == "GRACE_PERIOD":
        grace_until = claims.get("grace_until")
        if isinstance(grace_until, bool) or not isinstance(grace_until, (int, float)):
            raise LicenseTokenError("Grace-period end is invalid")
        if grace_until <= datetime.now(timezone.utc).timestamp():
            raise LicenseTokenError("Grace period has expired")
    return claims


def _write_key(path: Path, contents: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(contents)


def generate_keypair(private_key_path: Path, public_key_path: Path, passphrase: str) -> None:
    if len(passphrase) < 16:
        raise ValueError("Private key passphrase must contain at least 16 characters")
    if private_key_path.resolve() == public_key_path.resolve():
        raise ValueError("Private and public key paths must differ")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase.encode()),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _write_key(private_key_path, private_pem, 0o600)
    try:
        _write_key(public_key_path, public_pem, 0o644)
    except Exception:
        private_key_path.unlink(missing_ok=True)
        raise


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use an ISO-8601 timestamp with a timezone, e.g. 2027-01-01T00:00:00Z") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def issue_license(
    private_key_path: Path,
    customer_id: str,
    status: str,
    expires_at: datetime,
    grace_until: datetime | None,
    passphrase: str,
) -> str:
    if status not in LICENSE_STATUSES:
        raise ValueError("Unsupported license status")
    if not customer_id.strip():
        raise ValueError("Customer identifier must not be empty")
    if status == "GRACE_PERIOD" and grace_until is None:
        raise ValueError("GRACE_PERIOD licenses require --grace-until")
    if expires_at <= datetime.now(timezone.utc):
        raise ValueError("License expiry must be in the future")
    if grace_until is not None and grace_until <= datetime.now(timezone.utc):
        raise ValueError("Grace period must end in the future")
    if grace_until is not None and grace_until > expires_at:
        raise ValueError("--grace-until must be no later than --expires")
    private_key = serialization.load_pem_private_key(
        private_key_path.read_bytes(),
        password=passphrase.encode(),
    )
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": customer_id.strip(),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires_at,
        "license_status": status,
    }
    if grace_until is not None:
        claims["grace_until"] = grace_until
    return jwt.encode(claims, private_key, algorithm="RS256")


def main() -> int:
    parser = argparse.ArgumentParser(description="ClinicPulse RSA license key and token tool")
    commands = parser.add_subparsers(dest="command", required=True)

    keygen = commands.add_parser("generate-keypair", help="Create an issuer keypair")
    keygen.add_argument("--private-key", type=Path, required=True)
    keygen.add_argument("--public-key", type=Path, required=True)

    issue = commands.add_parser("issue", help="Sign a ClinicPulse license token")
    issue.add_argument("--private-key", type=Path, required=True)
    issue.add_argument("--customer-id", required=True)
    issue.add_argument("--status", choices=sorted(LICENSE_STATUSES), default="PAID")
    issue.add_argument("--expires", type=_parse_timestamp, required=True)
    issue.add_argument("--grace-until", type=_parse_timestamp)

    args = parser.parse_args()
    try:
        if args.command == "generate-keypair":
            passphrase = getpass.getpass("New private-key passphrase (minimum 16 characters): ")
            confirmation = getpass.getpass("Repeat passphrase: ")
            if passphrase != confirmation:
                raise ValueError("Passphrases do not match")
            generate_keypair(args.private_key, args.public_key, passphrase)
            print(f"Public key written to {args.public_key}; protect and back up the private key.")
            return 0
        passphrase = getpass.getpass("Private-key passphrase: ")
        print(issue_license(
            args.private_key, args.customer_id, args.status,
            args.expires, args.grace_until, passphrase,
        ))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Licensing tool error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
