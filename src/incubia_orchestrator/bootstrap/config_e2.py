"""Compatibility import for composition code."""
from incubia_orchestrator.foundation.config_e2 import (E2Budget, InvalidE2Configuration,
                                                        load_budgets, load_capabilities,
                                                        load_profiles)

__all__ = ["E2Budget", "InvalidE2Configuration", "load_budgets", "load_capabilities", "load_profiles"]
