"""Read-only Google Drive v3 transport over httpx, with a service-account identity.

Implements ``DriveTransportPort`` and ``DriveIdentityPort`` for ``DriveSourceCatalog``.
The access token comes from the OAuth JWT-bearer grant signed with the service
account key (``google-auth`` signs only; httpx does every request). Scope is
fixed to ``drive.readonly``. Errors are sanitized: no file names, URLs, emails,
tokens or provider bodies reach a message.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import time
from typing import Callable

import httpx

from incubia_orchestrator.modules.knowledge.domain import (
    ExportRequest, ExportResult, ExportTooLargeError, IdentityNotVerifiedError, InventoryPage,
    SourceCatalogError, SourceRef)
from incubia_orchestrator.modules.knowledge.ports import VerifiedIdentity

DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_API = "https://www.googleapis.com/drive/v3"
_FIELDS = "id,name,mimeType,parents,version,modifiedTime,size,trashed,shortcutDetails/targetId"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ServiceAccountDriveIdentity:
    def __init__(self, client_email: str, token_uri: str, sign: Callable[[dict], bytes], *,
                 scopes: tuple[str, ...] = (DRIVE_READONLY,), client: httpx.Client | None = None):
        if scopes != (DRIVE_READONLY,):
            raise ValueError("Drive identity must be limited to drive.readonly")
        if not client_email or not token_uri.startswith("https://"):
            raise ValueError("Service account email and HTTPS token URI are required")
        self._email, self._token_uri, self._sign, self._scopes = client_email, token_uri, sign, scopes
        self._client = client or httpx.Client(timeout=15)
        self._token, self._expires_at = "", 0.0
        self._lock = Lock()

    @classmethod
    def from_file(cls, path: Path, *, client: httpx.Client | None = None) -> "ServiceAccountDriveIdentity":
        """Load a service-account JSON key; it must be a private (0600) file."""
        from google.auth import crypt, jwt

        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("Service account key must be an existing file with mode 0600")
        info = json.loads(path.read_text())
        if info.get("type") != "service_account":
            raise ValueError("Key file is not a service account key")
        signer = crypt.RSASigner.from_service_account_info(info)
        return cls(info["client_email"], info.get("token_uri", "https://oauth2.googleapis.com/token"),
                   lambda claims: jwt.encode(signer, claims), client=client)

    def access_token(self) -> str:
        with self._lock:
            if self._token and time() < self._expires_at - 60:
                return self._token
            now = int(time())
            assertion = self._sign({"iss": self._email, "scope": " ".join(self._scopes),
                                    "aud": self._token_uri, "iat": now, "exp": now + 3600})
            try:
                response = self._client.post(self._token_uri, data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion.decode() if isinstance(assertion, bytes) else assertion})
                response.raise_for_status()
                body = response.json()
                token, expires_in = body["access_token"], int(body.get("expires_in", 0))
            except Exception:
                raise IdentityNotVerifiedError("Drive service account token request failed") from None
            if not token or expires_in <= 60:
                raise IdentityNotVerifiedError("Drive service account token was not usable")
            self._token, self._expires_at = token, time() + expires_in
            return token

    def assert_verified(self) -> VerifiedIdentity:
        self.access_token()
        return VerifiedIdentity(sha256(self._email.encode()).hexdigest()[:16], self._scopes)


class HttpDriveTransport:
    def __init__(self, identity: ServiceAccountDriveIdentity, *, client: httpx.Client | None = None,
                 page_size: int = 1000):
        self._identity, self._page_size = identity, page_size
        self._client = client or httpx.Client(timeout=30)

    def _get(self, path: str, params: dict) -> httpx.Response:
        try:
            response = self._client.get(f"{DRIVE_API}{path}", params=params, headers={
                "Authorization": f"Bearer {self._identity.access_token()}"})
            response.raise_for_status()
            return response
        except SourceCatalogError:
            raise
        except httpx.HTTPStatusError as exc:
            raise SourceCatalogError(f"Drive request failed (HTTP {exc.response.status_code})") from None
        except Exception as exc:
            raise SourceCatalogError(f"Drive request failed ({type(exc).__name__})") from None

    def list_children(self, folder_id: str, page_token: str | None) -> InventoryPage:
        _require_id(folder_id)
        params = {"q": f"'{folder_id}' in parents", "fields": f"nextPageToken,files({_FIELDS})",
                  "pageSize": str(self._page_size), "supportsAllDrives": "true",
                  "includeItemsFromAllDrives": "true"}
        if page_token:
            params["pageToken"] = page_token
        body = self._get("/files", params).json()
        return InventoryPage(tuple(_ref(item) for item in body.get("files", ())),
                             body.get("nextPageToken") or None)

    def get_metadata(self, source_id: str) -> SourceRef:
        _require_id(source_id)
        return _ref(self._get(f"/files/{source_id}", {"fields": _FIELDS, "supportsAllDrives": "true"}).json())

    def export(self, request: ExportRequest) -> ExportResult:
        _require_id(request.source_id)
        content = self._get(f"/files/{request.source_id}/export",
                            {"mimeType": request.target_mime_type}).content
        if len(content) > request.max_bytes:
            raise ExportTooLargeError("Export content exceeds the configured size limit")
        return ExportResult(request.source_id, request.target_mime_type, content, sha256(content).hexdigest())


def _require_id(value: str) -> None:
    if not _ID_RE.match(value or ""):
        raise SourceCatalogError("Drive identifier is not a safe ID")


def _ref(item: dict) -> SourceRef:
    try:
        size = item.get("size")
        return SourceRef(
            source_id=item["id"], name=item.get("name", ""), mime_type=item["mimeType"],
            parents=tuple(item.get("parents") or ()), observed_version=str(item["version"]),
            modified_time=datetime.fromisoformat(item["modifiedTime"].replace("Z", "+00:00")),
            size_bytes=int(size) if size is not None else None, trashed=bool(item.get("trashed")),
            shortcut_target_id=(item.get("shortcutDetails") or {}).get("targetId"))
    except Exception:
        raise SourceCatalogError("Drive returned an unusable file record") from None
