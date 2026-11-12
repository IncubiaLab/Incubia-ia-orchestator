"""Bounded HTTP(S) document downloader with SSRF guards for signed URLs."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from incubia_orchestrator.modules.knowledge.domain import DocumentDownloadError, DocumentRejectedError


def _validate_public_ip(raw_ip: str) -> None:
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError as exc:
        raise DocumentRejectedError("Download target address is invalid") from exc
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
        or not addr.is_global
    ):
        raise DocumentRejectedError("Download URL resolves to a restricted network address")


def validate_download_url(
    url: str,
    *,
    allow_insecure_urls: bool = False,
    allow_private_network: bool = False,
) -> str:
    parts = urlsplit(url.strip())
    allowed_schemes = {"https", "http"} if allow_insecure_urls else {"https"}
    if parts.scheme.lower() not in allowed_schemes or not parts.hostname:
        raise DocumentRejectedError("Download URL scheme or host is not permitted")
    if parts.username or parts.password:
        raise DocumentRejectedError("Download URL must not embed credentials")

    hostname = parts.hostname
    if not allow_private_network:
        is_literal_ip = True
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            is_literal_ip = False
        if is_literal_ip:
            _validate_public_ip(hostname)
            return url
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise DocumentDownloadError("Unable to resolve document download host") from exc
        if not infos:
            raise DocumentDownloadError("Unable to resolve document download host")
        for info in infos:
            sockaddr = info[4]
            if sockaddr:
                _validate_public_ip(str(sockaddr[0]).split("%", 1)[0])
    return url


class HttpxDocumentDownloader:
    """Downloads a presigned object strictly within declared size limits without logging URLs."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        allow_insecure_urls: bool = False,
        allow_private_network: bool = False,
    ):
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._allow_insecure_urls = allow_insecure_urls
        self._allow_private_network = allow_private_network

    def download(self, url: str, *, declared_size_bytes: int, max_bytes: int) -> bytes:
        bound = min(declared_size_bytes, max_bytes)
        if bound < 1:
            raise DocumentRejectedError("Download size bound must be positive")

        current_url = validate_download_url(
            url,
            allow_insecure_urls=self._allow_insecure_urls,
            allow_private_network=self._allow_private_network,
        )

        owns_client = self._client is None
        client = self._client or httpx.Client(
            timeout=httpx.Timeout(self._timeout_seconds, connect=5.0),
            follow_redirects=False,
        )
        try:
            for _ in range(3):
                with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DocumentDownloadError("Document download redirect missed location")
                        current_url = validate_download_url(
                            urljoin(current_url, location),
                            allow_insecure_urls=self._allow_insecure_urls,
                            allow_private_network=self._allow_private_network,
                        )
                        continue
                    if response.status_code != 200:
                        raise DocumentDownloadError(
                            f"Document download returned status {response.status_code}"
                        )
                    header_len = response.headers.get("content-length")
                    if header_len is not None:
                        try:
                            if int(header_len) > bound:
                                raise DocumentRejectedError(
                                    "Document Content-Length exceeds declared sizeBytes"
                                )
                        except ValueError:
                            pass
                    buffer = bytearray()
                    for chunk in response.iter_bytes():
                        if len(buffer) + len(chunk) > bound:
                            raise DocumentRejectedError(
                                "Downloaded content exceeded declared sizeBytes limit"
                            )
                        buffer.extend(chunk)
                    return bytes(buffer)
            raise DocumentDownloadError("Document download exceeded redirect limit")
        except (DocumentDownloadError, DocumentRejectedError):
            raise
        except httpx.HTTPError as exc:
            # Never propagate raw httpx exceptions because they embed the signed download URL.
            raise DocumentDownloadError(
                f"Document download transport error ({type(exc).__name__})"
            ) from None
        finally:
            if owns_client:
                client.close()
