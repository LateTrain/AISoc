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
