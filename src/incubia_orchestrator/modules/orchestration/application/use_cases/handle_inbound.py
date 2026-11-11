"""Application orchestration for a neutral inbound message."""
from typing import Callable
from uuid import uuid4

from incubia_orchestrator.foundation.contracts.execution import (
    CompletedExecution, ExecutionInput, ExecutionOutput, ExecutionScope, StartExecutionRequest,
)
from incubia_orchestrator.modules.orchestration.application.capability_resolver import CapabilityResolver
from incubia_orchestrator.modules.orchestration.application.context_builder import ContextBuilder
from incubia_orchestrator.modules.orchestration.application.selection import NoEligibleAgent, select
from incubia_orchestrator.modules.orchestration.domain.profile import SpecialtyProfile
from incubia_orchestrator.modules.orchestration.domain.routing import RouteStatus
from incubia_orchestrator.modules.orchestration.ports.agent_discovery import AgentDiscoveryPort
from incubia_orchestrator.modules.orchestration.ports.workflow_runtime import WorkflowRuntimePort
from incubia_orchestrator.modules.orchestration.application.grounded_response import GroundedResponse


class HandleInbound:
    """Resuelve capacidad, agente y contexto antes de iniciar un mensaje entrante."""

    def __init__(self, resolver: CapabilityResolver, discovery: AgentDiscoveryPort, context_builder: ContextBuilder,
                 profiles: dict[tuple[str, int], SpecialtyProfile], runtime: WorkflowRuntimePort,
                 new_id: Callable[[], str] = lambda: str(uuid4()),
                 grounded: GroundedResponse | None = None):
        self._resolver, self._discovery, self._context_builder = resolver, discovery, context_builder
        self._profiles, self._runtime, self._new_id = profiles, runtime, new_id
        self._grounded = grounded

    def __call__(self, text: str, scope: ExecutionScope):
        """Devuelve None si no hay ruta o agente elegible; si lo hay, ejecuta su perfil."""
        eligible = frozenset(capability for profile in self._profiles.values() for capability in profile.capabilities)
        decision = self._resolver.resolve(text, eligible)
        if decision.status is not RouteStatus.RESOLVED:
            return None
        try:
            descriptor = select(self._discovery.find(decision.capability or "", scope))
        except NoEligibleAgent:
            return None
        profile = self._profiles[(descriptor.profile_id, descriptor.profile_version)]
        context = self._context_builder.build(scope, profile, text)
        if self._grounded is not None:
            request_id, execution_id = self._new_id(), self._new_id()
            answer = self._grounded.answer(scope, context.user_text, decision.capability or "",
                                           execution_id=execution_id)
            return CompletedExecution(request_id, execution_id,
                                      ExecutionOutput(answer.text, specialty=profile.specialty,
                                                      public_references=answer.public_references))
        return self._runtime.start(StartExecutionRequest(self._new_id(), self._new_id(), scope,
                                   ExecutionInput(text, history=context.history), profile.specialty))
