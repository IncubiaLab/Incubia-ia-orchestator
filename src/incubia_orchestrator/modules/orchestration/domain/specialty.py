from incubia_orchestrator.foundation.contracts.specialty import Specialty
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    specialty: Specialty
    purpose: str
    instructions: str
    model: str


def profiles_for(model: str) -> dict[Specialty, Profile]:
    if not model.strip():
        raise ValueError("El modelo no puede estar vacío")
    return {
        Specialty.GENERAL: Profile(Specialty.GENERAL, "Consultas generales",
            "Eres el especialista general. Empieza con 'Hola, soy el especialista general.' Responde brevemente en español; no afirmes tener acceso a sistemas externos.", model),
        Specialty.VENTAS: Profile(Specialty.VENTAS, "Consultas de ventas",
            "Eres el especialista en ventas. Empieza con 'Hola, soy el especialista en ventas.' Ayuda con oportunidades, clientes, propuestas y cierre; no inventes datos de clientes.", model),
        Specialty.MARKETING: Profile(Specialty.MARKETING, "Consultas de marketing",
            "Eres el especialista en marketing. Empieza con 'Hola, soy el especialista en marketing.' Ayuda con campañas, audiencia, canales y mensajes; no inventes métricas.", model),
    }
