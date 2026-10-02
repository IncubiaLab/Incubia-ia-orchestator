import re
from dataclasses import dataclass
from incubia_orchestrator.foundation.contracts.specialty import Specialty


@dataclass(frozen=True)
class Route:
    specialty: Specialty
    reason: str


_VENTAS = frozenset({"venta", "ventas", "vender", "cliente", "clientes", "cotizacion", "cotizaciones", "prospecto", "prospectos", "negociacion", "cierre", "comercial"})
_MARKETING = frozenset({"marketing", "campana", "campanas", "publicidad", "anuncio", "anuncios", "audiencia", "marca", "branding", "segmentacion", "redes", "seo"})


def route(text: str) -> Route:
    import unicodedata
    normalized = "".join(char for char in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(char))
    words = set(re.findall(r"[a-z]+", normalized))
    ventas = bool(words & _VENTAS)
    marketing = bool(words & _MARKETING)
    if ventas and marketing:
        return Route(Specialty.GENERAL, "ambiguous")
    if ventas:
        return Route(Specialty.VENTAS, "sales_terms")
    if marketing:
        return Route(Specialty.MARKETING, "marketing_terms")
    return Route(Specialty.GENERAL, "fallback")
