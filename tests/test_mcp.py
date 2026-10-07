import asyncio
import unittest
from soc.mcp_client import demo, connect, call

class MCPTests(unittest.TestCase):
    def test_real_process_discovery_and_evidence(self):
        trace = demo('alert-1')
        self.assertFalse(any(s['step'] == 'Error' for s in trace), trace)
        calls = [s for s in trace if s['step'] == 'MCP tools/call']
        self.assertEqual([c['tool'] for c in calls], ['server_info', 'get_alert', 'get_user', 'query_login_events'])
        import json
        server_pid = json.loads(calls[0]['result']['content'][0]['text'])['pid']
        self.assertNotEqual(server_pid, trace[0]['client_pid'])
        self.assertIn('e3', calls[-1]['result']['content'][0]['text'])

    def test_tool_error_is_a_protocol_result(self):
        async def check():
            trace = []
            async with connect(trace) as (session, _):
                _, error = await call(session, 'get_user', {'user_id': 'missing'}, trace, 'test')
                self.assertTrue(error)
        asyncio.run(check())

class DeviceEvidenceTests(unittest.TestCase):
    def test_device_source_real_mcp_each_scenario(self):
        from soc.device_data import DEVICE_HISTORY
        from soc.data import SCENARIOS
        async def check():
            async with connect([]) as (session, tools):
                self.assertIn('get_device_history', {t.name for t in tools})
                for scenario in SCENARIOS.values():
                    uid = scenario['user']['id']
                    data, error = await call(session, 'get_device_history', {'user_id': uid}, [], 'test')
                    self.assertFalse(error)
                    self.assertEqual(data['device_history'], DEVICE_HISTORY[uid])
                    self.assertNotIn('device_history', scenario)
                _, error = await call(session, 'get_device_history', {'user_id': 'missing'}, [], 'test')
                self.assertTrue(error)
        asyncio.run(check())
        self.assertFalse(DEVICE_HISTORY['u-101'][0]['familiar'])
        self.assertTrue(DEVICE_HISTORY['u-102'][0]['familiar'])
        self.assertIsNone(DEVICE_HISTORY['u-104'][0]['familiar'])

    def test_scope_rejects_other_users_and_extra_args(self):
        from soc.mcp_client import arguments_in_scope
        meta = {'alert_id': 'alert-1', 'user_id': 'u-101'}
        self.assertTrue(arguments_in_scope('get_device_history', {'user_id': 'u-101'}, meta))
        self.assertFalse(arguments_in_scope('get_device_history', {'user_id': 'u-102'}, meta))
        self.assertFalse(arguments_in_scope('get_device_history', {'user_id': 'u-101', 'extra': 1}, meta))
        self.assertFalse(arguments_in_scope('get_alert', {'alert_id': 'alert-2'}, meta))
        self.assertFalse(arguments_in_scope('server_info', {}, meta))

    def test_model_collection_success_and_rejection(self):
        import json
        import httpx
        from unittest.mock import patch, AsyncMock
        from soc.mcp_client import gather
        from soc.core import build_request
        from soc.data import SCENARIOS
        request = build_request('Investigate', SCENARIOS['Possible compromise'], 'test')
        request['messages'][1]['content'] = 'Alert metadata:\n' + json.dumps({'alert_id': 'alert-1', 'user_id': 'u-101'})
        calls = [{'function': {'name': name, 'arguments': {'user_id': uid}}} for name, uid in [
            ('get_device_history', 'u-102'), ('get_user', 'u-101'),
            ('query_login_events', 'u-101'), ('get_device_history', 'u-101')]]
        bodies = [{'message': {'role': 'assistant', 'content': '', 'tool_calls': calls}},
                  {'message': {'role': 'assistant', 'content': 'done'}}]
        trace = []
        async def check():
            with patch('soc.mcp_client.httpx.AsyncClient') as client:
                mock = AsyncMock()
                mock.post.side_effect = [httpx.Response(200, json=b, request=httpx.Request('POST', 'http://test')) for b in bodies]
                client.return_value.__aenter__.return_value = mock
                return await gather(request, 'http://test', trace)
        evidence = asyncio.run(check())
        self.assertEqual(len(evidence['events']), 3)
        self.assertEqual(evidence['device_history'][0]['id'], 'device-u101-1')
        self.assertEqual(len([t for t in trace if t['step'] == 'Rejected tool']), 1)
        self.assertFalse(any(t.get('tool') == 'get_device_history' and t.get('arguments', {}).get('user_id') == 'u-102' for t in trace if t['step'] == 'MCP tools/call'))
        from soc.evidence_summary import summarize_mcp
        summary = summarize_mcp({'mcp_trace': trace, 'evidence_collected': evidence})
        self.assertEqual(summary['event_count'], 3)
        self.assertEqual(summary['device_count'], 1)
        self.assertTrue(summary['user_fetched'])
        self.assertEqual(len(summary['problems']), 1)
        self.assertFalse(any(c['tool'] == 'server_info' for c in summary['successful_calls']))

    def test_citations_only_accept_retrieved_devices(self):
        from soc.core import Investigation, citation_check
        result = Investigation(summary='test', findings=[{'claim': 'unfamiliar', 'evidence_ids': ['device-u101-1']}], uncertainty=[], next_steps=[])
        self.assertEqual(citation_check(result, {'events': [], 'device_history': [{'id': 'device-u101-1'}]})['unknown_evidence_ids'], [])
        self.assertEqual(citation_check(result, {'events': []})['unknown_evidence_ids'], ['device-u101-1'])

    def test_summary_failed_and_legacy_records(self):
        from soc.evidence_summary import summarize_mcp
        legacy = {'mcp_trace': [{'step': 'MCP tools/call', 'source': 'Model requested', 'tool': 'get_device_history',
                                'result': {'isError': True, 'content': [{'type': 'text', 'text': 'failed'}]}}]}
        summary = summarize_mcp(legacy)
        self.assertFalse(summary['device_called'])
        self.assertEqual(summary['successful_calls'], [])
        self.assertEqual(len(summary['problems']), 1)
        self.assertTrue(summary['warnings'])
        self.assertEqual(summarize_mcp({})['event_count'], 0)

    def test_final_request_receives_collected_device_only(self):
        import json
        import tempfile
        import httpx
        from pathlib import Path
        from unittest.mock import patch
        from soc.core import investigate
        from soc.data import SCENARIOS
        collected = {'alert': 'test', 'user': {'id': 'u-101'}, 'events': [], 'device_history': [{'id': 'device-u101-1', 'familiar': False}]}
        output = {'summary': 'test', 'findings': [{'claim': 'unfamiliar', 'evidence_ids': ['device-u101-1']}], 'uncertainty': [], 'next_steps': []}
        with tempfile.TemporaryDirectory() as tmp, patch('soc.mcp_client.gather_evidence', return_value=collected), patch('soc.core.httpx.Client') as client:
            client.return_value.__enter__.return_value.post.return_value = httpx.Response(200, json={'message': {'content': json.dumps(output)}}, request=httpx.Request('POST', 'http://test'))
            run = investigate('Investigate', SCENARIOS['Possible compromise'], 'test', 'http://test', scenario='Possible compromise', mcp_mode=True, path=Path(tmp)/'test.db')
        self.assertNotIn('device-u101', run['initial_request']['messages'][1]['content'])
        supplied = json.loads(run['request']['messages'][1]['content'].split('\n', 1)[1])
        self.assertEqual(supplied, collected)
        self.assertEqual(run['checks']['unknown_evidence_ids'], [])
