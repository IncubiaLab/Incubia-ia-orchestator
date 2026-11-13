"""Pure domain guardrails and 3-layer RBAC access-tier policy helpers."""
from __future__ import annotations

from dataclasses import dataclass
import re

from incubia_orchestrator.modules.identity_tenant.domain.principal import Role

CAPA1_DENIAL_MESSAGE = (
    "No puedo procesar esta solicitud porque infringe las políticas globales de seguridad "
    "(acceso restringido a contraseñas, secretos, datos personales sensibles de usuarios o "
    "configuración interna del sistema/OpenAI)."
)

# Capa 1 input patterns (normalized lowercase / case-insensitive).
_CAPA1_SECRET_REQUEST = re.compile(
    r"(?i)\b("
    r"contrase[ñn]a(?:s)?|password(?:s)?|passwd|clave(?:s)?\s+de\s+acceso|"
    r"api[\s_-]?key(?:s)?|secret[\s_-]?key(?:s)?|token(?:s)?\s+(?:de\s+)?(?:acceso|auth|bearer|gateway|bot)|"
    r"openai[\s_-]?api[\s_-]?key|database[\s_-]?url|connection[\s_-]?string|dsn|"
    r"credencial(?:es)?|llave(?:s)?\s+privada(?:s)?|private[\s_-]?key(?:s)?|"
    r"variables?\s+de\s+entorno|\.env\b"
    r")\b"
)

_CAPA1_OPENAI_INTERNAL = re.compile(
    r"(?i)(?:"
    r"\b(?:system\s+prompt|prompt\s+del\s+sistema|instrucciones\s+internas|reglas\s+ocultas)\b|"
    r"\b(?:configuraci[oó]n|detalles|datos|par[aá]metros|cuenta|billing|org(?:anization)?\s*id|key)\s+"
    r"(?:intern[oa]s?\s+)?(?:de\s+)?openai\b|"
    r"\bopenai\b.{0,40}\b(?:api[\s_-]?key|secret|token|billing|account|config|interno|internal|system\s+prompt)\b"
    r")"
)

_CAPA1_USER_PII = re.compile(
    r"(?i)(?:"
    r"\b(?:datos?\s+personal(?:es)?|informaci[oó]n\s+(?:personal|privada|sensible)|pii)\s+"
    r"(?:de\s+(?:los\s+)?usuarios?|de\s+otros?\s+usuarios?|de\s+clientes?)\b|"
    r"\b(?:dame|mu[eé]strame|lista(?:me)?|dime|obtener|exporta(?:r)?)\s+"
    r"(?:los\s+|las\s+)?(?:correos?|emails?|tel[eé]fonos?|celulares?|direcciones?|c[eé]dulas?|dni|ssn|datos\s+personales)\s+"
    r"(?:de\s+(?:los\s+)?usuarios?|de\s+todos)\b"
    r")"
)

# Capa 1 output secret patterns (redacted before returning to caller).
_SECRET_OUTPUT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bnpg_[A-Za-z0-9_-]{10,}\b"), "[REDACTED_DB_SECRET]"),
    (re.compile(r"postgres(?:ql)?://[^\s\"'<>]+"), "[REDACTED_DSN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b"), "Bearer [REDACTED_TOKEN]"),
    (
        re.compile(r"(?i)\b(?:OPENAI_API_KEY|DATABASE_URL|INCUBIA_ORCHESTRATOR_TOKEN|INCUBIA_ORBIT_GATEWAY_TOKEN)\s*=\s*\S+"),
        "[REDACTED_ENV_SECRET]",
    ),
)


@dataclass(frozen=True)
class GuardDecision:
    blocked: bool
    reason_code: str | None = None
    redacted_text: str | None = None


def allowed_access_tiers_for_role(role: Role) -> frozenset[str]:
    """Return cumulative Knowledge access tiers permitted for ``role``."""
    if role == Role.ADMIN:
        return frozenset({"workspace_general", "admin_only"})
    return frozenset({"workspace_general"})


def evaluate_capa1_input(text: str) -> GuardDecision:
    """Deterministically block Capa 1 requests before RAG or LLM execution."""
    if not text or not text.strip():
        return GuardDecision(blocked=False)
    if _CAPA1_OPENAI_INTERNAL.search(text):
        return GuardDecision(blocked=True, reason_code="CAPA1_OPENAI_INTERNAL_DENIED")
    if _CAPA1_SECRET_REQUEST.search(text):
        return GuardDecision(blocked=True, reason_code="CAPA1_SECRET_REQUEST_DENIED")
    if _CAPA1_USER_PII.search(text):
        return GuardDecision(blocked=True, reason_code="CAPA1_USER_PII_DENIED")
    return GuardDecision(blocked=False)


def sanitize_capa1_output(text: str) -> GuardDecision:
    """Redact any accidental credential or secret pattern from generated output."""
    if not text:
        return GuardDecision(blocked=False, redacted_text=text)
    sanitized = text
    redacted = False
    for pattern, replacement in _SECRET_OUTPUT_PATTERNS:
        updated, count = pattern.subn(replacement, sanitized)
        if count > 0:
            sanitized = updated
            redacted = True
    if redacted:
        return GuardDecision(
            blocked=False,
            reason_code="CAPA1_OUTPUT_SECRET_REDACTED",
            redacted_text=sanitized,
        )
    return GuardDecision(blocked=False, redacted_text=text)

