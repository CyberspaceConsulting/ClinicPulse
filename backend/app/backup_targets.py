"""Backup destinations: local directory, SFTP, WebDAV and S3-compatible storage."""
import base64
import hashlib
import io
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from .backup_core import BackupError, is_backup_filename

KINDS = ("local", "sftp", "webdav", "s3")
SECRET_FIELDS = {"password", "private_key", "secret_key"}
SECRET_MASK = "********"
TIMEOUT = 30

FIELDS: dict[str, dict[str, bool]] = {
    # field -> required
    "local": {"subdir": False},
    "sftp": {
        "host": True, "port": False, "username": True, "password": False,
        "private_key": False, "directory": False, "host_key_fingerprint": True,
    },
    "webdav": {"url": True, "username": False, "password": False},
    "s3": {
        "endpoint_url": False, "region": False, "bucket": True, "prefix": False,
        "access_key": True, "secret_key": True,
    },
}


@dataclass
class RemoteFile:
    name: str
    size: int
    modified: datetime | None


def backup_base_dir() -> Path:
    return Path(os.environ.get("MEDORA_BACKUP_DIR", "/backups"))


def validate_config(kind: str, config: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    if kind not in KINDS:
        raise BackupError("Unbekannter Zieltyp")
    cleaned: dict[str, Any] = {}
    for field, required in FIELDS[kind].items():
        value = config.get(field)
        if field in SECRET_FIELDS and value == SECRET_MASK and previous:
            value = previous.get(field)
        if isinstance(value, str):
            value = value.strip() if field != "private_key" else value.strip() + "\n" if value.strip() else ""
        if value in (None, ""):
            if required:
                raise BackupError(f"Das Feld „{field}“ ist erforderlich")
            continue
        cleaned[field] = value
    if kind == "local":
        subdir = str(cleaned.get("subdir", ""))
        if subdir.startswith("/") or ".." in Path(subdir).parts or "\\" in subdir:
            raise BackupError("Unterordner darf nicht außerhalb des Backup-Verzeichnisses liegen")
    if kind == "sftp":
        cleaned["port"] = int(cleaned.get("port", 22))
        if not 1 <= cleaned["port"] <= 65535:
            raise BackupError("Ungültiger Port")
        if "password" not in cleaned and "private_key" not in cleaned:
            raise BackupError("Passwort oder privater Schlüssel erforderlich")
        if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}=?", cleaned["host_key_fingerprint"]):
            raise BackupError("Host-Key-Fingerabdruck muss im Format SHA256:… angegeben werden")
    # Transport encryption is mandatory: plain HTTP is never accepted.
    if kind == "webdav" and urlparse(cleaned["url"]).scheme != "https":
        raise BackupError("Die WebDAV-URL muss mit https:// beginnen (verschlüsselte Übertragung ist Pflicht)")
    if kind == "s3" and "endpoint_url" in cleaned and urlparse(cleaned["endpoint_url"]).scheme != "https":
        raise BackupError("Der S3-Endpunkt muss mit https:// beginnen (verschlüsselte Übertragung ist Pflicht)")
    return cleaned


def mask_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: (SECRET_MASK if key in SECRET_FIELDS and value else value) for key, value in config.items()}


def parse_config(raw: str) -> dict[str, Any]:
    return json.loads(raw)


class Target:
    def upload(self, name: str, data: bytes) -> None: ...
    def list(self) -> list[RemoteFile]: ...
    def download(self, name: str) -> bytes: ...
    def delete(self, name: str) -> None: ...
    def test(self) -> None:
        self.list()


class LocalTarget(Target):
    def __init__(self, config: dict[str, Any]) -> None:
        base = backup_base_dir().resolve()
        self.directory = (base / str(config.get("subdir", ""))).resolve()
        if base != self.directory and base not in self.directory.parents:
            raise BackupError("Unterordner darf nicht außerhalb des Backup-Verzeichnisses liegen")

    def _path(self, name: str) -> Path:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        return self.directory / name

    def upload(self, name: str, data: bytes) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(name)
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(data)
        os.chmod(partial, 0o600)
        partial.replace(target)

    def list(self) -> list[RemoteFile]:
        if not self.directory.is_dir():
            return []
        files = []
        for entry in self.directory.iterdir():
            if entry.is_file() and is_backup_filename(entry.name):
                stat = entry.stat()
                files.append(RemoteFile(entry.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime).astimezone()))
        return files

    def download(self, name: str) -> bytes:
        try:
            return self._path(name).read_bytes()
        except OSError as exc:
            raise BackupError("Backup-Datei nicht gefunden") from exc

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def test(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        probe = self.directory / ".write-test"
        probe.write_bytes(b"ok")
        probe.unlink()


class SftpTarget(Target):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.directory = str(config.get("directory", ".")).rstrip("/") or "."

    def _connect(self):
        import paramiko

        transport = paramiko.Transport((self.config["host"], self.config["port"]))
        transport.banner_timeout = TIMEOUT
        try:
            transport.start_client(timeout=TIMEOUT)
            key = transport.get_remote_server_key()
            fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
            expected = self.config["host_key_fingerprint"].rstrip("=")
            if fingerprint != expected:
                raise BackupError(f"Host-Key stimmt nicht überein (Server meldet {fingerprint})")
            pkey = None
            if self.config.get("private_key"):
                for key_class in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
                    try:
                        pkey = key_class.from_private_key(io.StringIO(self.config["private_key"]), self.config.get("password"))
                        break
                    except (paramiko.SSHException, ValueError):
                        continue
                if pkey is None:
                    raise BackupError("Privater Schlüssel konnte nicht gelesen werden")
            transport.auth_publickey(self.config["username"], pkey) if pkey else transport.auth_password(
                self.config["username"], self.config["password"]
            )
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.get_channel().settimeout(TIMEOUT)
            return transport, sftp
        except BackupError:
            transport.close()
            raise
        except Exception as exc:
            transport.close()
            raise BackupError(f"SFTP-Verbindung fehlgeschlagen: {type(exc).__name__}") from exc

    def _run(self, action):
        transport, sftp = self._connect()
        try:
            return action(sftp)
        except BackupError:
            raise
        except Exception as exc:
            raise BackupError(f"SFTP-Fehler: {type(exc).__name__}") from exc
        finally:
            sftp.close()
            transport.close()

    def _remote(self, name: str) -> str:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        return f"{self.directory}/{name}"

    def upload(self, name: str, data: bytes) -> None:
        def action(sftp):
            self._makedirs(sftp)
            partial = self._remote(name) + ".part"
            with sftp.open(partial, "wb") as handle:
                handle.write(data)
            try:
                sftp.posix_rename(partial, self._remote(name))
            except OSError:
                sftp.rename(partial, self._remote(name))
        self._run(action)

    def _makedirs(self, sftp) -> None:
        if self.directory in {".", ""}:
            return
        current = "/" if self.directory.startswith("/") else ""
        for part in [item for item in self.directory.split("/") if item]:
            current = f"{current}{part}" if current in {"", "/"} else f"{current}/{part}"
            try:
                sftp.stat(current)
            except OSError:
                sftp.mkdir(current)

    def list(self) -> list[RemoteFile]:
        def action(sftp):
            try:
                entries = sftp.listdir_attr(self.directory)
            except OSError:
                return []
            return [
                RemoteFile(entry.filename, entry.st_size or 0, datetime.fromtimestamp(entry.st_mtime).astimezone() if entry.st_mtime else None)
                for entry in entries if is_backup_filename(entry.filename)
            ]
        return self._run(action)

    def download(self, name: str) -> bytes:
        def action(sftp):
            with sftp.open(self._remote(name), "rb") as handle:
                return handle.read()
        return self._run(action)

    def delete(self, name: str) -> None:
        self._run(lambda sftp: sftp.remove(self._remote(name)))

    def test(self) -> None:
        def action(sftp):
            self._makedirs(sftp)
            sftp.listdir(self.directory)
        self._run(action)


class WebDavTarget(Target):
    def __init__(self, config: dict[str, Any]) -> None:
        self.base = config["url"].rstrip("/") + "/"
        self.auth = (config["username"], config.get("password", "")) if config.get("username") else None

    def _request(self, method: str, name: str = "", **kwargs):
        import httpx

        try:
            return httpx.request(
                method, self.base + quote(name), auth=self.auth, timeout=TIMEOUT, follow_redirects=False, verify=True, **kwargs
            )
        except httpx.HTTPError as exc:
            raise BackupError(f"WebDAV-Verbindung fehlgeschlagen: {type(exc).__name__}") from exc

    def _check(self, response, ok: tuple[int, ...]) -> None:
        if response.status_code not in ok:
            raise BackupError(f"WebDAV-Server antwortete mit HTTP {response.status_code}")

    def upload(self, name: str, data: bytes) -> None:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        self._check(self._request("PUT", name, content=data), (200, 201, 204))

    def list(self) -> list[RemoteFile]:
        response = self._request("PROPFIND", headers={"Depth": "1"})
        if response.status_code == 404:
            return []
        self._check(response, (200, 207))
        files = []
        ns = {"d": "DAV:"}
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise BackupError("WebDAV-Antwort konnte nicht gelesen werden") from exc
        for item in root.findall("d:response", ns):
            href = item.findtext("d:href", default="", namespaces=ns)
            name = unquote(urlparse(href).path.rstrip("/").rsplit("/", 1)[-1])
            if not is_backup_filename(name):
                continue
            size = item.findtext(".//d:getcontentlength", default="0", namespaces=ns)
            files.append(RemoteFile(name, int(size) if size.isdigit() else 0, None))
        return files

    def download(self, name: str) -> bytes:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        response = self._request("GET", name)
        self._check(response, (200,))
        return response.content

    def delete(self, name: str) -> None:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        self._check(self._request("DELETE", name), (200, 204, 404))


class S3Target(Target):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.prefix = str(config.get("prefix", "")).strip("/")
        self.prefix = f"{self.prefix}/" if self.prefix else ""

    def _client(self):
        import boto3
        from botocore.config import Config

        return boto3.client(
            "s3",
            use_ssl=True,
            verify=True,
            endpoint_url=self.config.get("endpoint_url"),
            region_name=self.config.get("region") or "us-east-1",
            aws_access_key_id=self.config["access_key"],
            aws_secret_access_key=self.config["secret_key"],
            config=Config(connect_timeout=TIMEOUT, read_timeout=TIMEOUT, retries={"max_attempts": 2}),
        )

    def _run(self, action):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            return action(self._client())
        except (BotoCoreError, ClientError) as exc:
            code = exc.response.get("Error", {}).get("Code", "") if isinstance(exc, ClientError) else type(exc).__name__
            raise BackupError(f"S3-Fehler: {code}") from exc

    def _key(self, name: str) -> str:
        if not is_backup_filename(name):
            raise BackupError("Ungültiger Dateiname")
        return self.prefix + name

    def upload(self, name: str, data: bytes) -> None:
        self._run(lambda client: client.put_object(Bucket=self.config["bucket"], Key=self._key(name), Body=data))

    def list(self) -> list[RemoteFile]:
        def action(client):
            files = []
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.config["bucket"], Prefix=self.prefix):
                for item in page.get("Contents", []):
                    name = item["Key"][len(self.prefix):]
                    if is_backup_filename(name):
                        files.append(RemoteFile(name, item["Size"], item["LastModified"]))
            return files
        return self._run(action)

    def download(self, name: str) -> bytes:
        return self._run(lambda client: client.get_object(Bucket=self.config["bucket"], Key=self._key(name))["Body"].read())

    def delete(self, name: str) -> None:
        self._run(lambda client: client.delete_object(Bucket=self.config["bucket"], Key=self._key(name)))


def open_target(kind: str, config: dict[str, Any]) -> Target:
    return {"local": LocalTarget, "sftp": SftpTarget, "webdav": WebDavTarget, "s3": S3Target}[kind](config)
