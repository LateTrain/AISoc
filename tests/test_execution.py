import unittest
from soc.execution import execution_events, graph_dot

class ExecutionTests(unittest.TestCase):
    def test_repeated_turns_tools_and_stop(self):
        trace = [
            {'step': 'Model tool selection', 'turn': 1, 'response': {'message': {'tool_calls': [{'function': {'name': 'get_user'}}]}}},
            {'step': 'MCP tools/call', 'tool': 'get_user', 'result': {'isError': False}},
            {'step': 'Model tool selection', 'turn': 2, 'response': {'message': {'tool_calls': [{'function': {'name': 'get_user'}}]}}},
            {'step': 'Rejected tool', 'tool': 'get_user'},
            {'step': 'Model tool selection', 'turn': 3, 'response': {'message': {}}},
            {'step': 'Gathering stopped', 'reason': 'No more tools requested'},
            {'step': 'Final structured generation'},
        ]
        events = execution_events({'mcp_trace': trace, 'response': {'message': {}}, 'schema_valid': True, 'checks': {'unknown_evidence_ids': ['bad']}})
        self.assertEqual([e['status'] for e in events if e['kind'] == 'tool'], ['success', 'rejected'])
        self.assertEqual(len([e for e in events if e['kind'] == 'model']), 3)
        self.assertEqual(len([e for e in events if e['kind'] == 'stop']), 1)
        self.assertEqual(events[-1]['status'], 'warning')
        self.assertNotIn('get_device_history', graph_dot(events))

    def test_legacy_stop_and_process_inspection(self):
        events = execution_events({'mcp_trace': [
            {'step': 'MCP tools/call', 'tool': 'server_info', 'result': {'isError': False}},
            {'step': 'Model tool selection', 'turn': 1, 'response': {'message': {}}},
        ]})
        self.assertEqual(events[0]['status'], 'unknown')
        self.assertEqual(events[-1]['title'], 'No more tools requested')
        self.assertFalse(any(e['kind'] == 'tool' for e in events))

    def test_limit_failure_and_missing_results(self):
        events = execution_events({'mcp_trace': [
            {'step': 'MCP tools/call', 'tool': 'get_user'},
            {'step': 'Tool call limit reached', 'limit': 6},
        ], 'error': 'timeout'})
        self.assertEqual(next(e for e in events if e['kind'] == 'tool')['status'], 'unknown')
        self.assertEqual(next(e for e in events if e['kind'] == 'stop')['status'], 'warning')
        self.assertEqual(events[-1]['title'], 'Run failed')

    def test_incremental_ids_remain_stable(self):
        trace = [{'step': 'Launch server'}, {'step': 'MCP initialize'}]
        before = execution_events({'mcp_trace': trace})
        after = execution_events({'mcp_trace': trace + [{'step': 'MCP tools/list'}]})
        self.assertEqual(before, after[:len(before)])

    def test_direct_flow_includes_submission_model_checks_and_storage(self):
        run = {'mode': 'direct', 'submission': {'question': 'test'}, 'initial_request': {'messages': []},
               'generation_started': True, 'request': {'model': 'test'}, 'response': {'message': {'content': '{}'}},
               'schema_valid': True, 'checks': {'unknown_evidence_ids': []},
               'persistence': {'status': 'saved', 'destination': 'test.db'}}
        events = execution_events(run)
        self.assertEqual([e['kind'] for e in events], ['submission', 'input', 'generation', 'response', 'validation', 'validation', 'storage'])
        self.assertIn('reference evidence', events[1]['title'])
        self.assertFalse(any(e['kind'] == 'tool' for e in events))

    def test_gathering_failure_does_not_claim_final_model_call(self):
        events = execution_events({'mode': 'mcp', 'generation_started': False, 'error': 'MCP timeout',
                                  'persistence': {'status': 'saved'}})
        self.assertFalse(any(e['kind'] == 'generation' for e in events))
        self.assertEqual(events[-2]['status'], 'failed')
        self.assertEqual(events[-1]['kind'], 'storage')
