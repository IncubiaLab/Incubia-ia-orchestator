"""Opt-in real READ campaign for the selected Open Food Facts source.

This script performs one public product lookup only when explicitly enabled.
It never accepts a provider URL or tenant/deployment scope from the request.
"""

import json
import os
import sys

from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.audit.adapters.memory import InMemoryAuditLog
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import (
    Authority,
    InProcessPolicyEngine,
)
from incubia_orchestrator.modules.orchestration.adapters.tools.openfoodfacts import OpenFoodFactsAdapter
from incubia_orchestrator.modules.orchestration.adapters.tools.registry import (
    InProcessToolAdapterRegistry,
    InProcessToolExecutor,
    InProcessToolRegistry,
)
from incubia_orchestrator.modules.orchestration.application.execute_tool import ExecuteTool
from incubia_orchestrator.modules.orchestration.domain.tools import ToolDescriptor, ToolInvocation


TOOL_ID = "business.catalog.lookup"
SCOPE = ExecutionScope("local", "demo", "e3-read-campaign", "e3-read-operator")


def main() -> int:
    if os.getenv("INCUBIA_E3_READ_REAL") != "1":
        print("Set INCUBIA_E3_READ_REAL=1 to run the one-request real READ campaign.", file=sys.stderr)
        return 2
    product_ref = os.getenv("INCUBIA_E3_READ_PRODUCT_REF", "3017620422003")
    descriptor = ToolDescriptor(
        tool_id=TOOL_ID,
        version="2.0",
        capabilities=frozenset({TOOL_ID}),
        deployment_ids=frozenset({SCOPE.deployment_id}),
        tenant_ids=frozenset({SCOPE.tenant_id}),
        adapter_key="catalog.openfoodfacts",
        input_schema={
            "type": "object",
            "required": ["product_ref"],
            "additionalProperties": False,
            "properties": {"product_ref": {"type": "string", "maxLength": 18}},
        },
    )
    adapter = OpenFoodFactsAdapter()
    audit = InMemoryAuditLog()
    use_case = ExecuteTool(
        InProcessToolRegistry((descriptor,)),
        InProcessToolExecutor(InProcessToolAdapterRegistry({"catalog.openfoodfacts": adapter})),
        InProcessPolicyEngine(Authority(
            SCOPE.deployment_id,
            SCOPE.tenant_id,
            frozenset({SCOPE.actor_id}),
            enabled_actions=frozenset({TOOL_ID}),
        )),
        audit,
    )
    try:
        result = use_case(ToolInvocation(
            "e3-read-tool-call",
            "e3-read-execution",
            SCOPE,
            TOOL_ID,
            {"product_ref": product_ref},
            "tenant:demo:catalog",
            tool_version="2.0",
        ))
    finally:
        adapter.close()
    payload = {
        "status": result.status.value,
        "attempts": result.attempts,
        "error": result.error.code if result.error else None,
        "output": result.output,
        "audit_events": len(audit.events),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if result.status.value == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
