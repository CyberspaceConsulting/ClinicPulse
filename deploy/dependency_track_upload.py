#!/usr/bin/env python3
"""Download one release SBOM and submit it to a local Dependency-Track instance."""

import argparse
import base64
import getpass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ASSET = "medora.cdx.json"
TAG_PATTERN = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_sbom(directory: Path) -> bytes:
    data = (directory / ASSET).read_bytes()
    checksum_lines = (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    matches = [
        match.group(1).lower()
        for line in checksum_lines
        if (match := re.fullmatch(r"([0-9a-fA-F]{64}) [ *]medora\.cdx\.json", line))
    ]
    if len(matches) != 1 or hashlib.sha256(data).hexdigest() != matches[0]:
        raise ValueError("Die SHA256-Prüfsumme der SBOM fehlt oder stimmt nicht.")
    bom = json.loads(data)
    if not isinstance(bom, dict) or bom.get("bomFormat") != "CycloneDX" or bom.get("specVersion") != "1.5":
        raise ValueError("Das Release enthält keine unterstützte CycloneDX-1.5-SBOM.")
    if not isinstance(bom.get("components"), list) or not bom["components"]:
        raise ValueError("Die SBOM enthält keine Komponenten.")
    return data


def local_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Die API-Adresse muss eine lokale HTTP(S)-Adresse ohne Pfad sein.")
    return value.rstrip("/")


def upload_sbom(api_url: str, api_key: str, tag: str, sbom: bytes) -> str:
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise ValueError("Der Dependency-Track-API-Schlüssel ist leer oder ungültig.")
    payload = json.dumps({
        "autoCreate": True,
        "projectName": "Medora",
        "projectVersion": tag,
        "bom": base64.b64encode(sbom).decode("ascii"),
    }).encode("utf-8")
    request = Request(
        local_api_url(api_url) + "/api/v1/bom",
        data=payload,
        headers={"Content-Type": "application/json", "X-Api-Key": api_key},
        method="PUT",
    )
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not isinstance(result.get("token"), str) or not result["token"]:
        raise ValueError("Dependency-Track hat keinen Verarbeitungstoken zurückgegeben.")
    return result["token"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Release-Tag, z. B. v0.1.0")
    parser.add_argument("--api-url", default="http://127.0.0.1:8081", help="Lokale Dependency-Track-API")
    args = parser.parse_args()
    try:
        if not TAG_PATTERN.fullmatch(args.tag):
            raise ValueError("Ungültiger Release-Tag (erwartet z. B. v0.1.0).")
        local_api_url(args.api_url)
        with tempfile.TemporaryDirectory(prefix="medora-sbom-") as directory:
            subprocess.run(
                [
                    "gh", "release", "download", args.tag, "--repo", "CyberspaceConsulting/Medora",
                    "--pattern", ASSET, "--pattern", "SHA256SUMS", "--dir", directory,
                ],
                check=True,
            )
            sbom = verify_sbom(Path(directory))
        api_key = getpass.getpass("Dependency-Track API-Schlüssel: ")
        token = upload_sbom(args.api_url, api_key, args.tag, sbom)
        print(f"SBOM für Medora {args.tag} angenommen. Verarbeitungstoken: {token}")
        print("Die Analyse erfolgt asynchron; Ergebnis in Dependency-Track prüfen.")
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, URLError, HTTPError) as exc:
        print(f"SBOM-Upload fehlgeschlagen: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
