import os
from pathlib import Path
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

REAL_MAX_OUTPUT_TOKENS = 128
REAL_MAX_MESSAGE_CHARS = 500
REAL_MAX_TURNS = 2


def _load_local_env() -> None:
    """Load only the two supported local settings without overriding the shell."""
    path = Path(os.getenv("INCUBIA_ENV_FILE", ".env"))
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"OPENAI_API_KEY", "INCUBIA_MODEL"}:
            os.environ.setdefault(key, value.strip().strip('"\''))


def compose(*, fake: bool, model: str | None = None, max_output_tokens: int = REAL_MAX_OUTPUT_TOKENS,
            timeout: float = 30, retries: int = 0) -> HandleMessage:
    if max_output_tokens < 1 or timeout <= 0 or retries < 0:
        raise ValueError("Invalid model limits")
    if not fake:
        _load_local_env()
    selected_model = model or os.getenv("INCUBIA_MODEL") or "gpt-4o-mini"
    profiles = profiles_for(selected_model)
    if fake:
        llm = FakeLLM()
    else:
        if max_output_tokens > REAL_MAX_OUTPUT_TOKENS or retries != 0:
            raise ValueError("Límite real: hasta 128 tokens de salida y cero reintentos")
        from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
        from incubia_orchestrator.modules.orchestration.adapters.llm.monthly_limit import MonthlyCallLimiter
        budget_path = Path(os.getenv("INCUBIA_BUDGET_FILE", str(Path.home() / ".local/state/incubia/api-budget.json")))
        llm = OpenAILLM(model=selected_model,
                        api_key=os.getenv("OPENAI_API_KEY", ""), timeout=timeout, retries=retries,
                        limiter=MonthlyCallLimiter(budget_path))
    scope = ExecutionScope("local", "local", str(uuid4()), "local-user")
    policy = InProcessPolicyEngine(Authority("local", "local", frozenset({"local-user"})))
    return HandleMessage(LangGraphRuntimeAdapter(build_graph(
        make_node(llm, policy, max_output_tokens, profiles), select_specialty)), scope)
