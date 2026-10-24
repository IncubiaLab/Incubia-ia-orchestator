"""Contract for the httpx Drive v3 transport and service-account identity (offline)."""
from __future__ import annotations

import json
from hashlib import sha256
from urllib.parse import parse_qs

import httpx
import pytest

from incubia_orchestrator.modules.knowledge.adapters.drive_http import (
    DRIVE_READONLY, HttpDriveTransport, ServiceAccountDriveIdentity)
from incubia_orchestrator.modules.knowledge.domain import (
    ExportRequest, ExportTooLargeError, SourceCatalogError)

EMAIL = "kb-reader@proj.iam.gserviceaccount.com"
TOKEN_URI = "https://oauth2.googleapis.com/token"
DOC = "application/vnd.google-apps.document"


def _file(id_, name="n", mime=DOC, parents=("root1",), **extra):
    return {"id": id_, "name": name, "mimeType": mime, "parents": list(parents), "version": "7",
            "modifiedTime": "2026-10-20T10:00:00.000Z", **extra}


class Drive:
    """Minimal fake of the token endpoint and Drive v3."""

    def __init__(self, pages=None, export_body=b"# T\n\nhola\n", token_status=200):
        self.pages = pages or {}
        self.export_body, self.token_status = export_body, token_status
        self.token_calls, self.requests = 0, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == TOKEN_URI:
            self.token_calls += 1
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
            return httpx.Response(self.token_status, json={"access_token": "tok-SECRET", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok-SECRET"
        path, params = request.url.path, request.url.params
        if path == "/drive/v3/files":
            folder = params["q"].split("'")[1]
            token = params.get("pageToken")
            pages = self.pages[folder]
            index = int(token) if token else 0
            body = {"files": pages[index]}
            if index + 1 < len(pages):
                body["nextPageToken"] = str(index + 1)
            return httpx.Response(200, json=body)
        if path.endswith("/export"):
            return httpx.Response(200, content=self.export_body)
        if path.startswith("/drive/v3/files/"):
            return httpx.Response(200, json=_file(path.rsplit("/", 1)[1]))
        return httpx.Response(404)


def _identity(drive, scopes=(DRIVE_READONLY,)):
    client = httpx.Client(transport=httpx.MockTransport(drive))
    return ServiceAccountDriveIdentity(EMAIL, TOKEN_URI, lambda claims: b"signed." + json.dumps(claims).encode(),
                                       scopes=scopes, client=client), client


def test_identity_returns_opaque_digest_and_caches_token():
    drive = Drive()
    identity, _ = _identity(drive)
    verified = identity.assert_verified()
    assert verified.principal_digest == sha256(EMAIL.encode()).hexdigest()[:16]
    assert EMAIL not in repr(verified)
    assert verified.granted_scopes == (DRIVE_READONLY,)
    identity.access_token()
    assert drive.token_calls == 1


def test_identity_rejects_write_scopes():
    with pytest.raises(ValueError):
        _identity(Drive(), scopes=("https://www.googleapis.com/auth/drive",))


def test_identity_failure_is_sanitized():
    identity, _ = _identity(Drive(token_status=401))
    with pytest.raises(SourceCatalogError) as error:
        identity.assert_verified()
    assert EMAIL not in str(error.value) and "tok-" not in str(error.value)


def test_list_children_paginates_and_maps_fields():
    drive = Drive(pages={"root1": [[_file("a")], [_file("b", size="12"), _file("c", trashed=True)]]})
    identity, client = _identity(drive)
    transport = HttpDriveTransport(identity, client=client)
    first = transport.list_children("root1", None)
    second = transport.list_children("root1", first.next_page_token)
    assert [i.source_id for i in first.items] == ["a"] and second.next_page_token is None
    assert second.items[0].size_bytes == 12 and second.items[1].trashed
    assert second.items[0].observed_version == "7" and second.items[0].parents == ("root1",)
    query = drive.requests[1].url.params
    assert query["supportsAllDrives"] == "true" and "trashed" in query["fields"]


def test_list_rejects_unsafe_folder_id():
    identity, client = _identity(Drive())
    with pytest.raises(SourceCatalogError):
        HttpDriveTransport(identity, client=client).list_children("x' or '1'='1", None)


def test_shortcut_target_is_mapped():
    drive = Drive(pages={"root1": [[_file("s", mime="application/vnd.google-apps.shortcut",
                                          shortcutDetails={"targetId": "t1"})]]})
    identity, client = _identity(drive)
    item = HttpDriveTransport(identity, client=client).list_children("root1", None).items[0]
    assert item.shortcut_target_id == "t1"


def test_export_returns_hashed_bytes():
    drive = Drive(export_body=b"# Hola\n")
    identity, client = _identity(drive)
    result = HttpDriveTransport(identity, client=client).export(
        ExportRequest("doc1", DOC, "text/markdown", 1000))
    assert result.content == b"# Hola\n" and result.sha256 == sha256(b"# Hola\n").hexdigest()
    assert drive.requests[-1].url.params["mimeType"] == "text/markdown"


def test_export_over_limit_raises():
    identity, client = _identity(Drive(export_body=b"x" * 50))
    with pytest.raises(ExportTooLargeError):
        HttpDriveTransport(identity, client=client).export(ExportRequest("doc1", DOC, "text/markdown", 10))


def test_http_errors_are_sanitized():
    def broken(request):
        if str(request.url) == TOKEN_URI:
            return httpx.Response(200, json={"access_token": "tok-SECRET", "expires_in": 3600})
        return httpx.Response(500, text="Internal secret-file-name.docx")
    client = httpx.Client(transport=httpx.MockTransport(broken))
    identity = ServiceAccountDriveIdentity(EMAIL, TOKEN_URI, lambda c: b"s", client=client)
    with pytest.raises(SourceCatalogError) as error:
        HttpDriveTransport(identity, client=client).get_metadata("doc1")
    assert "secret-file-name" not in str(error.value)
