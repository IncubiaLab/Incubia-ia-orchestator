#!/usr/bin/env python3
"""Full E3-3 campaign: exercise the governed READ tool through the PEP.

Runs five cases through `ExecuteTool` (the Policy Enforcement Point): ALLOW via
an injected adapter, DENY, INDETERMINATE, REQUIRE_APPROVAL and invalid input.
Every non-ALLOW case must make zero calls into the injected adapter. Evidence:
a sanitized JSON artifact (gate_closed is always false; the owner still has to
ratify budget/operations per docs/roadmap/etapa-3/VERIFICACION.md).

    python scripts/e3/run_e3_3_campaign.py --dry-run     # plan only, touches nothing
    INCUBIA_E3_3_CAMPAIGN=1 INCUBIA_E3_3_BUDGET_APPROVED=1 INCUBIA_E3_3_BUDGET_USD=0.01 INCUBIA_E3_READ_REAL=1 \
        python scripts/e3/run_e3_3_campaign.py

The ALLOW case always runs through whatever adapter is injected via `Deps`; in
production that defaults to the real `OpenFoodFactsAdapter`. Tests inject their
own adapter (e.g. the in-repo `FakeCatalogAdapter`) and never touch the network.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.adapters.memory import InMemoryAuditLog
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyDecision
from incubia_orchestrator.modules.orchestration.adapters.tools.openfoodfacts import OpenFoodFactsAdapter
from incubia_orchestrator.modules.orchestration.adapters.tools.registry import (
    InProcessToolAdapterRegistry, InProcessToolExecutor, InProcessToolRegistry,
)
from incubia_orchestrator.modules.orchestration.application.execute_tool import ExecuteTool
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor, ToolInvocation

ROOT = Path(__file__).resolve().parents[2]

TOOL_ID = "business.catalog.lookup"
ADAPTER_KEY = "catalog.openfoodfacts"
DEPLOYMENT_ID = "e3-3-campaign"
TENANT_ID = "e3-3-campaign"
ACTOR_ID = "e3-3-campaign-actor"
DEFAULT_PRODUCT_REF = "3017620422003"
MIN_BUDGET_USD = 0.01
CASE_NAMES = ("allow", "deny", "indeterminate", "require_approval", "invalid_input")


class GuardError(RuntimeError):
    """A safety precondition failed; nothing was touched."""


@dataclass(frozen=True)
class Guarded:
    budget_usd: float


def check_guards(env: dict) -> Guarded:
    """Fail closed unless this campaign and its budget are explicitly approved."""
    if env.get("INCUBIA_E3_3_CAMPAIGN") != "1":
        raise GuardError("Set INCUBIA_E3_3_CAMPAIGN=1 to authorize the E3-3 campaign")
    if env.get("INCUBIA_E3_3_BUDGET_APPROVED") != "1":
        raise GuardError("Set INCUBIA_E3_3_BUDGET_APPROVED=1 once the budget is approved")
    try:
        budget = float(env.get("INCUBIA_E3_3_BUDGET_USD", ""))
    except ValueError:
        budget = float("nan")
    if not (math.isfinite(budget) and budget >= MIN_BUDGET_USD):
        raise GuardError("INCUBIA_E3_3_BUDGET_USD must be a finite approved amount (>= 0.01)")
    return Guarded(budget)


@dataclass
class Deps:
    """The adapter under test; tests inject a fake, production uses the real one."""
    adapter: object = None

    def fill(self, env: dict) -> "Deps":
        if self.adapter is None:
            if env.get("INCUBIA_E3_READ_REAL") != "1":
                raise GuardError("Set INCUBIA_E3_READ_REAL=1 to authorize the real Open Food Facts READ")
            self.adapter = OpenFoodFactsAdapter()
        return self


class _CountingAdapter:
    """Wraps any injected adapter so every case can prove exactly how many
    physical calls reached it, regardless of whether the adapter instruments
    itself."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def execute(self, invocation, descriptor, *, credential=None, audit=None):
        self.calls += 1
        return self._inner.execute(invocation, descriptor, credential=credential, audit=audit)


class _FixedPolicy:
    """Minimal PolicyEnginePort returning one fixed decision; proves ExecuteTool's
    own safety behavior for effects InProcessPolicyEngine never produces."""

    def __init__(self, effect: Effect):
        self._effect = effect

    def evaluate(self, query) -> PolicyDecision:
        return PolicyDecision(str(uuid4()), self._effect, ("E3_3_FIXED",), (), ("e3-3-campaign",), "e3-3-1")


class _UnreachablePolicy:
    """Proves invalid input is rejected before policy is ever consulted."""

    def evaluate(self, query) -> PolicyDecision:
        raise AssertionError("policy must not be evaluated for invalid input")


@dataclass(frozen=True)
class Case:
    name: str
    policy: object
    input_data: dict


def _descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        TOOL_ID, version="2.0", capabilities=frozenset({TOOL_ID}),
        deployment_ids=frozenset({DEPLOYMENT_ID}), tenant_ids=frozenset({TENANT_ID}),
        adapter_key=ADAPTER_KEY,
        input_schema={"type": "object", "required": ["product_ref"], "additionalProperties": False,
                      "properties": {"product_ref": {"type": "string", "maxLength": 18}}},
    )


def build_cases(product_ref: str) -> tuple[Case, ...]:
    allow_policy = InProcessPolicyEngine(Authority(DEPLOYMENT_ID, TENANT_ID, frozenset({ACTOR_ID}),
                                                    enabled_actions=frozenset({TOOL_ID})))
    deny_policy = InProcessPolicyEngine(Authority(DEPLOYMENT_ID, TENANT_ID, frozenset({ACTOR_ID}),
                                                   enabled_actions=frozenset()))
    valid_input = {"product_ref": product_ref}
    return (
        Case("allow", allow_policy, valid_input),
        Case("deny", deny_policy, valid_input),
        Case("indeterminate", _FixedPolicy(Effect.INDETERMINATE), valid_input),
        Case("require_approval", _FixedPolicy(Effect.REQUIRE_APPROVAL), valid_input),
        Case("invalid_input", _UnreachablePolicy(), {}),
    )


def _run_case(case: Case, descriptor: ToolDescriptor, adapter: _CountingAdapter) -> dict:
    audit = InMemoryAuditLog()
    executor = InProcessToolExecutor(InProcessToolAdapterRegistry({ADAPTER_KEY: adapter}))
    use_case = ExecuteTool(InProcessToolRegistry((descriptor,)), executor, case.policy, audit)
    scope = ExecutionScope(DEPLOYMENT_ID, TENANT_ID, f"e3-3-{case.name}", ACTOR_ID)
    invocation = ToolInvocation(
        f"e3-3-{case.name}-call", f"e3-3-{case.name}-execution", scope, TOOL_ID, case.input_data,
        resource=f"tenant:{TENANT_ID}:catalog", tool_version=descriptor.version,
    )
    before = adapter.calls
    result = use_case(invocation)
    return {
        "name": case.name,
        "status": result.status.value,
        "error": result.error.code if result.error else None,
        "audit_events": len(audit.events),
        "adapter_calls_during_case": adapter.calls - before,
    }


def run_campaign(deps: Deps, *, product_ref: str = DEFAULT_PRODUCT_REF, env: dict | None = None) -> dict:
    deps = deps.fill(env or {})
    adapter = _CountingAdapter(deps.adapter)
    descriptor = _descriptor()
    results = [_run_case(case, descriptor, adapter) for case in build_cases(product_ref)]
    allow = next(r for r in results if r["name"] == "allow")
    non_allow = [r for r in results if r["name"] != "allow"]
    allow_ok = allow["status"] == "SUCCESS" and allow["adapter_calls_during_case"] == 1
    zero_call_safety = all(r["adapter_calls_during_case"] == 0 for r in non_allow)
    return {
        "gate": "E3-3", "gate_closed": False, "generated_at": datetime.now(UTC).isoformat(),
        "product_ref": product_ref, "cases": results,
        "allow_executed_via_adapter": allow_ok, "zero_call_safety": zero_call_safety,
        "total_adapter_calls": adapter.calls,
        "note": "gate_closed stays false: closing E3-3 is the owner's decision after reviewing this evidence.",
    }


# ------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Full E3-3 campaign (governed READ through the PEP)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    p.add_argument("--date", default=datetime.now(UTC).strftime("%Y-%m-%d"))
    p.add_argument("--output-path", type=Path, default=None, help="artifact path (default keeps history per date)")
    p.add_argument("--product-ref", default=DEFAULT_PRODUCT_REF)
    return p


def default_output_path(date: str) -> Path:
    return ROOT / "evals/results" / f"e3-3-{date}.json"


def build_plan(args) -> dict:
    return {
        "dry_run": args.dry_run,
        "cases": list(CASE_NAMES),
        "required_env": ["INCUBIA_E3_3_CAMPAIGN=1", "INCUBIA_E3_3_BUDGET_APPROVED=1", "INCUBIA_E3_3_BUDGET_USD=<amount>=0.01", "INCUBIA_E3_READ_REAL=1"],
        "output_path": str(args.output_path or default_output_path(args.date)),
    }


def main(argv: list[str] | None = None, *, deps: Deps | None = None, env: dict | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = build_plan(args)
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    merged = dict(os.environ if env is None else env)
    try:
        guarded = check_guards(merged)
    except GuardError as exc:
        print(f"Refusing E3-3 campaign: {exc}", file=sys.stderr)
        return 2
    try:
        report = run_campaign(deps or Deps(), product_ref=args.product_ref, env=merged)
    except GuardError as exc:
        print(f"Refusing E3-3 campaign: {exc}", file=sys.stderr)
        return 2
    report["budget_usd_approved"] = guarded.budget_usd
    output_path = args.output_path or default_output_path(args.date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"zero_call_safety": report["zero_call_safety"],
                      "allow_executed_via_adapter": report["allow_executed_via_adapter"],
                      "gate_closed": False, "output_path": str(output_path)}, indent=2))
    return 0 if (report["zero_call_safety"] and report["allow_executed_via_adapter"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
