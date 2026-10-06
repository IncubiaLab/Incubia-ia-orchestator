from dataclasses import dataclass

from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.foundation.config_e2 import load_capabilities, load_profiles
from pathlib import Path


@dataclass(frozen=True)
class Profile:
    specialty: Specialty
    purpose: str
    instructions: str
    model: str


def profiles_for(model: str) -> dict[Specialty, Profile]:
    if not model.strip():
        raise ValueError("El modelo no puede estar vacío")
    root = Path(__file__).resolve().parents[5] / "config" / "e2"
    configured = load_profiles(root / "profiles", load_capabilities(root))
    return {specialty: Profile(specialty, profile.purpose, profile.instructions, model)
            for specialty, profile in configured.items()}
