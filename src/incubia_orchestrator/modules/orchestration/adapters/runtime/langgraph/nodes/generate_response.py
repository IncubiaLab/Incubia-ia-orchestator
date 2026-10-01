import logging
from incubia_orchestrator.modules.governance.domain.policy import Effect, PolicyQuery
from incubia_orchestrator.modules.governance.ports.policy_engine import PolicyEnginePort
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure, GenerationRequest, LLMPort
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.state import GraphState

LOG = logging.getLogger(__name__)


def make_node(llm: LLMPort, policy: PolicyEnginePort, max_output_tokens: int):
    def generate(state: GraphState) -> GraphState:
        scope = state["scope"]
        try:
            decision = policy.evaluate(PolicyQuery(scope.actor_id, "llm.generate", "configured-llm",
                                                   scope, state["execution_id"]))
        except Exception:
            return {"error_code": "POLICY_UNAVAILABLE"}
        LOG.info("policy decision=%s revision=%s effect=%s", decision.decision_id,
                 decision.policy_revision, decision.effect)
        if decision.effect == Effect.DENY:
            return {"reply": "No autorizado para generar respuesta.", "denied": True}
        if decision.effect == Effect.REQUIRE_APPROVAL:
            return {"error_code": "APPROVAL_UNSUPPORTED"}
        if decision.effect != Effect.ALLOW or decision.obligations:
            return {"error_code": "POLICY_INDETERMINATE"}
        try:
            response = llm.generate(GenerationRequest(state["text"], state["history"],
                                                      "Responde de forma clara y breve.", max_output_tokens))
            if not response.text.strip():
                return {"error_code": "EMPTY_RESPONSE"}
            return {"reply": response.text}
        except GenerationFailure as exc:
            return {"error_code": exc.code}
    return generate
