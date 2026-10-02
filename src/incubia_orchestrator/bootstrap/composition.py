import os
from uuid import uuid4
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
from incubia_orchestrator.modules.orchestration.adapters.llm.fake import FakeLLM
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.adapter import LangGraphRuntimeAdapter
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.graph import build_graph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response import make_node
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.select_specialty import select_specialty
from incubia_orchestrator.modules.orchestration.application.use_cases.handle_message import HandleMessage
from incubia_orchestrator.modules.orchestration.domain.specialty import profiles_for


def compose(*, fake: bool, model: str | None = None, max_output_tokens: int = 512,
            timeout: float = 30, retries: int = 0) -> HandleMessage:
    if max_output_tokens < 1 or timeout <= 0 or retries < 0:
        raise ValueError("Invalid model limits")
    selected_model = model or os.getenv("INCUBIA_MODEL") or "gpt-4o-mini"
    profiles = profiles_for(selected_model)
    if fake:
        llm = FakeLLM()
    else:
        from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
        llm = OpenAILLM(model=selected_model,
                        api_key=os.getenv("OPENAI_API_KEY", ""), timeout=timeout, retries=retries)
    scope = ExecutionScope("local", "local", str(uuid4()), "local-user")
    policy = InProcessPolicyEngine(Authority("local", "local", frozenset({"local-user"})))
    return HandleMessage(LangGraphRuntimeAdapter(build_graph(
        make_node(llm, policy, max_output_tokens, profiles), select_specialty)), scope)
