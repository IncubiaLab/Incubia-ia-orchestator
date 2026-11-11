import re
import unicodedata
from dataclasses import dataclass
from incubia_orchestrator.foundation.contracts.specialty import Specialty


def _normalize(text: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKD", text.casefold())
                    if not unicodedata.combining(character))


def _ngrams(tokens: list[str], n: int = 2) -> set[str]:
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


@dataclass(frozen=True)
class Route:
    specialty: Specialty
    reason: str


_VENTAS = frozenset({"venta", "ventas", "vender", "cliente", "clientes", "cotizacion", "cotizaciones", "prospecto", "prospectos", "negociacion", "cierre", "comercial"})
_MARKETING = frozenset({"marketing", "campana", "campanas", "publicidad", "anuncio", "anuncios", "audiencia", "marca", "branding", "segmentacion", "redes", "seo"})


def route(text: str) -> Route:
    tokens = re.findall(r"[a-z]+", _normalize(text))
    grams = _ngrams(tokens)
    terms = set(tokens) | {" ".join(gram) for gram in grams}
    ventas = bool(terms & _VENTAS)
    marketing = bool(terms & _MARKETING)

    if ventas and marketing:
        return Route(Specialty.GENERAL, "ambiguous")
    if ventas:
        return Route(Specialty.VENTAS, "sales_terms")
    if marketing:
        return Route(Specialty.MARKETING, "marketing_terms")
    return Route(Specialty.GENERAL, "fallback")
