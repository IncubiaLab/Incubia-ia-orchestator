"""Strict loading of public configuration; no infrastructure dependency."""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from incubia_orchestrator.foundation.contracts.specialty import Specialty
from incubia_orchestrator.modules.orchestration.domain.profile import ContextBudget, SpecialtyProfile


class InvalidE2Configuration(ValueError):
    pass


@dataclass(frozen=True)
class E2Budget:
    max_calls_per_month: int
    max_output_tokens: int
    usd_cap: float | None = None


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise InvalidE2Configuration(f"Cannot read {path.name}") from exc


def _mapping(raw: Any, allowed: set[str], name: str) -> dict:
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise InvalidE2Configuration(f"Invalid fields in {name}")
    return raw


def load_capabilities(root: Path) -> frozenset[str]:
    raw = _mapping(_load_yaml(root / "capabilities.yaml"), {"contract_version", "capabilities"}, "capabilities")
    values = raw.get("capabilities")
    if raw.get("contract_version") != 1 or not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values) or len(values) != len(set(values)):
        raise InvalidE2Configuration("Invalid capabilities catalog")
    return frozenset(values)


def load_profiles(root: Path, capabilities: frozenset[str] | None = None) -> dict[Specialty, SpecialtyProfile]:
    capabilities = capabilities or load_capabilities(root.parent)
    expected = {"profile_id", "profile_version", "specialty", "purpose", "instructions", "style", "capabilities", "exclusions", "required_fields", "optional_fields", "output_contract", "budget"}
    budget_fields = {"max_input_tokens", "max_output_tokens", "max_history_pairs", "max_context_items"}
    profiles: dict[Specialty, SpecialtyProfile] = {}
    ids: set[tuple[str, int]] = set()
    for path in sorted(root.glob("*.yaml")):
        raw = _mapping(_load_yaml(path), expected, path.name)
        if set(raw) != expected:
            raise InvalidE2Configuration(f"Incomplete profile: {path.name}")
        budget = _mapping(raw["budget"], budget_fields, f"budget in {path.name}")
        if set(budget) != budget_fields:
            raise InvalidE2Configuration(f"Incomplete budget: {path.name}")
        try:
            profile = SpecialtyProfile(raw["profile_id"], raw["profile_version"], Specialty(raw["specialty"]), raw["purpose"], raw["instructions"], raw["style"], frozenset(raw["capabilities"]), frozenset(raw["exclusions"]), tuple(raw["required_fields"]), tuple(raw["optional_fields"]), raw["output_contract"], ContextBudget(**budget))
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidE2Configuration(f"Invalid profile: {path.name}") from exc
        if not profile.capabilities <= capabilities:
            raise InvalidE2Configuration(f"Unknown capability in {path.name}")
        key = (profile.profile_id, profile.profile_version)
        if key in ids or profile.specialty in profiles:
            raise InvalidE2Configuration(f"Duplicate profile in {path.name}")
        ids.add(key)
        profiles[profile.specialty] = profile
    if set(profiles) != set(Specialty):
        raise InvalidE2Configuration("The three initial specialties must be configured")
    return profiles


def load_budgets(path: Path, *, mode: str | None = None) -> dict[str, E2Budget]:
    raw = _mapping(_load_yaml(path), {"contract_version", "budgets"}, "budgets")
    if raw.get("contract_version") != 1 or not isinstance(raw.get("budgets"), dict):
        raise InvalidE2Configuration("Invalid budgets")
    loaded: dict[str, E2Budget] = {}
    for name, value in raw["budgets"].items():
        allowed = {"max_calls_per_month", "max_output_tokens"} | ({"usd_cap"} if name == "eval-e2" else set())
        value = _mapping(value, allowed, f"budget {name}")
        if not {"max_calls_per_month", "max_output_tokens"} <= set(value):
            raise InvalidE2Configuration(f"Incomplete budget {name}")
        try:
            loaded[name] = E2Budget(**value)
        except TypeError as exc:
            raise InvalidE2Configuration(f"Invalid budget {name}") from exc
    if mode == "eval-e2" and loaded.get("eval-e2", E2Budget(0, 0)).usd_cap is None:
        raise InvalidE2Configuration("eval-e2 requires a usd_cap")
    return loaded
