import hashlib
import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "dependency_track_upload.py"
spec = importlib.util.spec_from_file_location("dependency_track_upload", SCRIPT)
upload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upload)


@pytest.fixture
def release_files(tmp_path):
    sbom = json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "components": [{"name": "vue", "version": "3.0.0"}],
    }).encode()
    (tmp_path / upload.ASSET).write_bytes(sbom)
    digest = hashlib.sha256(sbom).hexdigest()
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  {upload.ASSET}\n", encoding="utf-8")
    return tmp_path, sbom


def test_release_sbom_checks_checksum_and_format(release_files):
    directory, sbom = release_files
    assert upload.verify_sbom(directory) == sbom
    (directory / upload.ASSET).write_bytes(sbom + b" ")
    with pytest.raises(ValueError, match="SHA256"):
        upload.verify_sbom(directory)


@pytest.mark.parametrize("url", [
    "https://example.com", "http://127.0.0.1.evil.example:8081",
    "http://localhost:8081/path", "http://user:password@localhost:8081",
    "http://localhost:8081?key=value",
])
def test_upload_refuses_nonlocal_or_invalid_address(url):
    with pytest.raises(ValueError, match="lokale"):
        upload.local_api_url(url)


def test_upload_sends_project_version_and_sbom_to_local_api(release_files):
    _, sbom = release_files
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            received["path"] = self.path
            received["key"] = self.headers["X-Api-Key"]
            received["payload"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"token":"test-processing-token"}')

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        token = upload.upload_sbom(
            f"http://127.0.0.1:{server.server_port}", "test-api-key", "v0.1.0", sbom,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    assert token == "test-processing-token"
    assert received["path"] == "/api/v1/bom"
    assert received["key"] == "test-api-key"
    assert received["payload"]["projectName"] == "Medora"
    assert received["payload"]["projectVersion"] == "v0.1.0"
    assert received["payload"]["autoCreate"] is True
    assert upload.base64.b64decode(received["payload"]["bom"]) == sbom
