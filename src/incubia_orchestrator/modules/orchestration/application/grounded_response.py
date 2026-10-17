"""Bounded evidence composition before a response is exposed to a channel."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from incubia_orchestrator.modules.knowledge.domain import EvidenceItem, RetrievalQuery
from incubia_orchestrator.modules.knowledge.ports import RetrievalPort
from incubia_orchestrator.foundation.contracts.execution import ExecutionScope
from incubia_orchestrator.foundation.public_references import safe_public_ref
from incubia_orchestrator.modules.orchestration.domain.tools import ToolInvocation, ToolStatus


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    evidence: tuple[EvidenceItem, ...]
    public_references: tuple[str, ...]
    abstained: bool


class GroundedResponse:
    """Only supplied, scoped evidence can support a factual response."""

    def __init__(self, retrieval: RetrievalPort, *, min_score: float = 0.2):
        self._retrieval = retrieval
        self._min_score = min_score

    @staticmethod
    def read_evidence(execute_tool, invocation: ToolInvocation) -> tuple[EvidenceItem, ...]:
        """Execute via the governed PEP and bound untrusted READ output."""
        result = execute_tool(invocation)
        if result.status is not ToolStatus.SUCCESS or not result.output:
            return ()
        if result.output.get("untrusted_content") is True:
            return ()
        raw = result.output.get("items")
        if not isinstance(raw, list):
            return ()
        evidence = []
        for index, entry in enumerate(raw[:5]):
            if not isinstance(entry, dict):
                continue
            description = entry.get("description") or entry.get("name") or entry.get("product_name")
            if not isinstance(description, str) or not description.strip():
                continue
            # Tool metadata is provenance, not a claim that the text is trusted.
            evidence.append(EvidenceItem(invocation.scope.deployment_id,
                                         result.source or result.tool_id,
                                         invocation.tool_version or "1",
                                         f"{invocation.tool_call_id}:{index}",
                                         invocation.tool_call_id, description[:1024],
                                         public_ref=safe_public_ref(result.external_reference or
                                                                    result.output.get("source_url"))))
        return tuple(evidence)

    def answer(self, scope: ExecutionScope, query: str, capability: str, *,
               deadline: datetime | None = None, tool_evidence: tuple[EvidenceItem, ...] = (),
               execution_id: str | None = None) -> GroundedAnswer:
        del execution_id  # Correlation is used by a coordinator when a Tool READ is present.
        if deadline is not None and datetime.now(timezone.utc) >= deadline:
            return GroundedAnswer("No tengo evidencia suficiente para responder.", (), (), True)
        retrieved = self._retrieval.retrieve(RetrievalQuery(scope, query, capability, deadline=deadline))
        candidates = tuple(item for item in (*retrieved, *tool_evidence)
                           if item.deployment_id == scope.deployment_id
                           and (item.score is None or item.score >= self._min_score))
        if not candidates:
            return GroundedAnswer("No tengo evidencia suficiente para responder.", (), (), True)
        versions = {}
        for item in candidates:
            previous = versions.setdefault(item.source_id, (item.source_version, item.text))
            if previous != (item.source_version, item.text):
                return GroundedAnswer("Las fuentes disponibles se contradicen; necesito verificar antes de responder.",
                                      (), (), True)
        if any(re.search(r"ignore\s+(?:all\s+)?previous|system\s+message|<\|(?:system|assistant)|"
                         r"ignora\s+(?:todas\s+)?(?:las\s+)?instrucciones|revela\s+(?:el\s+)?secreto",
                         item.text, re.I) for item in candidates):
            return GroundedAnswer("No tengo evidencia segura para responder.", (), (), True)
        # Extract the best Knowledge hit and reserve room for a governed READ.
        eligible = tuple(item for item in candidates if item in retrieved)[:1] + tuple(
            item for item in tool_evidence if item in candidates)[:4]
        # This is a deterministic extractive baseline. A generative adapter must
        # separately verify claims before it can replace this behavior.
        text = "\n".join(item.text for item in eligible)
        references = tuple(dict.fromkeys(ref for item in eligible
                                         if (ref := safe_public_ref(item.public_ref))))
        return GroundedAnswer(text, eligible, references, False)
