import json
import unittest
from pathlib import Path
from incubia_orchestrator.bootstrap.composition import compose
from incubia_orchestrator.modules.orchestration.application.router import route
from incubia_orchestrator.modules.orchestration.domain.specialty import Specialty, profiles_for
from incubia_orchestrator.foundation.contracts.execution import CompletedExecution, FailedExecution, to_dict, outcome_from_dict


class RoutingTests(unittest.TestCase):
    def test_validation_dataset(self):
        path = Path(__file__).resolve().parents[1] / 'evals' / 'routing-v1.jsonl'
        examples = [json.loads(line) for line in path.read_text().splitlines()]
        correct = sum(route(item['text']).specialty.value == item['expected'] for item in examples)
        self.assertGreaterEqual(correct / len(examples), .8)

    def test_shared_config_and_visible_selection(self):
        profiles = profiles_for('gpt-4o-mini')
        self.assertEqual(set(profiles), set(Specialty))
        self.assertEqual({p.model for p in profiles.values()}, {'gpt-4o-mini'})
        handle = compose(fake=True)
        for message, expected in [('hola', Specialty.GENERAL),
                                  ('quiero vender', Specialty.VENTAS),
                                  ('necesito una campaña', Specialty.MARKETING)]:
            outcome = handle(message)
            self.assertIsInstance(outcome, CompletedExecution)
            self.assertEqual(outcome.output.specialty, expected)
            self.assertIn(f'especialista en {expected.value}', outcome.output.text)
            self.assertEqual(outcome, outcome_from_dict(to_dict(outcome)))

    def test_failure_retains_selected_specialty(self):
        from incubia_orchestrator.modules.orchestration.adapters.llm.fake import FakeLLM
        from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.adapter import LangGraphRuntimeAdapter
        from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.graph import build_graph
        from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response import make_node
        from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.select_specialty import select_specialty
        from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import Authority, InProcessPolicyEngine
        from incubia_orchestrator.foundation.contracts.execution import ExecutionScope, ExecutionInput, StartExecutionRequest
        llm = FakeLLM('PROVIDER_TIMEOUT')
        policy = InProcessPolicyEngine(Authority('local', 'local', frozenset({'actor'})))
        graph = build_graph(make_node(llm, policy, 10, profiles_for('gpt-4o-mini')), select_specialty)
        request = StartExecutionRequest('r', 'e', ExecutionScope('local', 'local', 'c', 'actor'), ExecutionInput('quiero vender'))
        outcome = LangGraphRuntimeAdapter(graph).start(request)
        self.assertIsInstance(outcome, FailedExecution)
        self.assertEqual(outcome.error.specialty, Specialty.VENTAS)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(outcome, outcome_from_dict(to_dict(outcome)))


if __name__ == '__main__':
    unittest.main()
