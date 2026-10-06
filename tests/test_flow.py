import json
import unittest
import httpx
from incubia_orchestrator.foundation.contracts.execution import *
from incubia_orchestrator.modules.governance.domain.policy import *
from incubia_orchestrator.modules.governance.adapters.policy.in_process.engine import *
from incubia_orchestrator.modules.orchestration.adapters.llm.fake import FakeLLM
from incubia_orchestrator.modules.orchestration.adapters.llm.openai_adapter import OpenAILLM
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.graph import build_graph
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.adapter import LangGraphRuntimeAdapter
from incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response import make_node
from incubia_orchestrator.modules.orchestration.application.use_cases.handle_message import HandleMessage
from incubia_orchestrator.modules.orchestration.application.session import ConversationSession
from incubia_orchestrator.modules.orchestration.ports.llm import GenerationRequest, GenerationFailure

SCOPE = ExecutionScope('local', 'local', 'conversation', 'actor')


def runtime(llm, policy=None):
    policy = policy or InProcessPolicyEngine(Authority('local', 'local', frozenset({'actor'})))
    return LangGraphRuntimeAdapter(build_graph(make_node(llm, policy, 512)))


class FlowTests(unittest.TestCase):
    def test_round_trip(self):
        request = StartExecutionRequest('r', 'e', SCOPE, ExecutionInput('hola', history=(ConversationTurn('a', 'b'),)))
        self.assertEqual(request, request_from_dict(json.loads(json.dumps(to_dict(request)))))
        for outcome in (CompletedExecution('r', 'e', ExecutionOutput('ok')),
                        CompletedExecution('r', 'e', ExecutionOutput('ok', usage=TokenUsage(12, 3))),
                        SuspendedExecution('r', 'e', 'c'),
                        FailedExecution('r', 'e', ExecutionError('X', 'error'))):
            self.assertEqual(outcome, outcome_from_dict(json.loads(json.dumps(to_dict(outcome)))))

    def test_application_and_history(self):
        llm = FakeLLM()
        session = ConversationSession(HandleMessage(runtime(llm), SCOPE, lambda: 'id'), max_turns=2)
        for text in ('a', 'b', 'c'):
            self.assertIsInstance(session.send(text), CompletedExecution)
        self.assertEqual(len(llm.calls), 3)
        self.assertEqual([t.user for t in llm.calls[2].history], ['a', 'b'])
        self.assertEqual([t.user for t in session.history], ['b', 'c'])

    def test_application_uses_runtime_port_without_graph(self):
        calls = []
        class Runtime:
            def start(self, request):
                calls.append(request)
                return CompletedExecution(request.request_id, request.execution_id, ExecutionOutput('from-port'))
        outcome = HandleMessage(Runtime(), SCOPE, lambda: 'stable')('hola')
        self.assertEqual(outcome.output.text, 'from-port')
        self.assertEqual(calls[0].input.content, 'hola')
        self.assertEqual((calls[0].request_id, calls[0].execution_id), ('stable', 'stable'))

    def test_runtime_exception_is_safe(self):
        class BrokenGraph:
            def invoke(self, state):
                raise RuntimeError('secret-provider-detail')
        outcome = LangGraphRuntimeAdapter(BrokenGraph()).start(
            StartExecutionRequest('request', 'execution', SCOPE, ExecutionInput('hola')))
        self.assertEqual((outcome.request_id, outcome.execution_id), ('request', 'execution'))
        self.assertEqual(outcome.error.code, 'RUNTIME_ERROR')
        self.assertNotIn('secret-provider-detail', str(outcome))

    def test_policy_fail_closed(self):
        for effect in (Effect.DENY, Effect.INDETERMINATE, Effect.REQUIRE_APPROVAL):
            class Policy:
                def evaluate(self, query):
                    return PolicyDecision('d', effect, (), (), (), 'v1')
            llm = FakeLLM()
            outcome = runtime(llm, Policy()).start(StartExecutionRequest('r', 'e', SCOPE, ExecutionInput('x')))
            self.assertEqual(llm.calls, [])
            self.assertEqual(outcome.status, 'completed' if effect == Effect.DENY else 'failed')
        llm = FakeLLM()
        denied_scope = ExecutionScope('local', 'other', 'c', 'actor')
        self.assertEqual(runtime(llm).start(StartExecutionRequest('r', 'e', denied_scope, ExecutionInput('x'))).output.kind, 'policy_denied')
        self.assertEqual(llm.calls, [])

    def test_policy_error_fails_closed_without_generation(self):
        class BrokenPolicy:
            def evaluate(self, query):
                raise RuntimeError('secret-canary')
        llm = FakeLLM()
        outcome = runtime(llm, BrokenPolicy()).start(StartExecutionRequest('r', 'e', SCOPE, ExecutionInput('content-canary')))
        self.assertEqual(outcome.error.code, 'POLICY_UNAVAILABLE')
        self.assertEqual(llm.calls, [])
        self.assertNotIn('secret-canary', str(outcome))

    def test_policy_diagnostic_has_decision_without_content(self):
        llm = FakeLLM()
        with self.assertLogs('incubia_orchestrator.modules.orchestration.adapters.runtime.langgraph.nodes.generate_response', level='INFO') as logs:
            runtime(llm).start(StartExecutionRequest('r', 'e', SCOPE, ExecutionInput('content-canary')))
        diagnostic = ' '.join(logs.output)
        self.assertIn('revision=local-1', diagnostic)
        self.assertIn('decision=', diagnostic)
        self.assertNotIn('content-canary', diagnostic)

    def test_errors_and_resume(self):
        adapter = runtime(FakeLLM('PROVIDER_TIMEOUT'))
        outcome = adapter.start(StartExecutionRequest('r', 'e', SCOPE, ExecutionInput('x')))
        self.assertEqual((outcome.status, outcome.error.code, outcome.request_id), ('failed', 'PROVIDER_TIMEOUT', 'r'))
        self.assertEqual(adapter.resume(ResumeExecutionRequest('r', 'e', SCOPE, 'c')).error.code, 'RESUME_UNSUPPORTED')

    def test_provider_transport(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            if len(seen) == 1:
                return httpx.Response(429)
            return httpx.Response(200, json={'status': 'completed', 'usage': {'input_tokens': 12, 'output_tokens': 3}, 'output': [
                {'type': 'message', 'content': [{'type': 'output_text', 'text': 'respuesta'}]}]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = OpenAILLM(model='chosen-model', api_key='test-key', retries=1, client=client)
        response = provider.generate(GenerationRequest('hola', (ConversationTurn('a', 'b'),), 'instrucciones', 100))
        self.assertEqual(response.text, 'respuesta')
        self.assertEqual((response.usage.input_tokens, response.usage.output_tokens), (12, 3))
        self.assertEqual(len(seen), 2)
        self.assertFalse(seen[0]['store'])
        self.assertEqual([item['role'] for item in seen[0]['input']], ['user', 'assistant', 'user'])

    def test_provider_safe_errors(self):
        for status, code in ((401, 'PROVIDER_AUTH'), (429, 'PROVIDER_RATE_LIMIT'), (500, 'PROVIDER_ERROR')):
            client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))
            provider = OpenAILLM(model='chosen-model', api_key='secret', client=client)
            with self.assertRaises(GenerationFailure) as caught:
                provider.generate(GenerationRequest('x', (), 'i', 1))
            self.assertEqual(caught.exception.code, code)

    def test_provider_invalid_payload_is_safe(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
        provider = OpenAILLM(model='chosen-model', api_key='secret', client=client)
        with self.assertRaises(GenerationFailure) as caught:
            provider.generate(GenerationRequest('x', (), 'i', 1))
        self.assertEqual(caught.exception.code, 'PROVIDER_INVALID_RESPONSE')


if __name__ == '__main__':
    unittest.main()
