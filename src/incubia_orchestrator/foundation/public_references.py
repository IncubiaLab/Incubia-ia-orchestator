"""Allow only public, non-credentialed HTTPS references in outbound responses."""
from urllib.parse import urlsplit


def safe_public_ref(value: str | None) -> str | None:
    if not value or len(value) > 512:
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    if (parsed.hostname in {"localhost", "127.0.0.1"}
            or parsed.hostname.endswith((".internal", ".example.org", ".example.com", ".example.net"))):
        return None
    return value
