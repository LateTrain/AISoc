import unittest
from soc.data import SCENARIOS


class LoginFixtureTests(unittest.TestCase):
    def test_compromise_individual_attempts(self):
        events = SCENARIOS['Possible compromise']['events']
        logins = [e for e in events if e['type'] == 'login']
        self.assertEqual(sum(e['result'] == 'failure' for e in logins), 12)
        self.assertEqual(sum(e['result'] == 'success' for e in logins), 1)
        self.assertEqual(len({e['time'] for e in logins}), 13)
        self.assertEqual(len({e['id'] for e in events}), len(events))
        self.assertEqual([e['time'] for e in events], sorted(e['time'] for e in events))
        self.assertTrue(all('attempts' not in e for e in logins))
        self.assertEqual(next(e for e in events if e['id'] == 'e2')['result'], 'success')
        self.assertEqual(next(e for e in events if e['id'] == 'e3')['type'], 'download')

    def test_failed_attack_individual_attempts(self):
        events = SCENARIOS['Failed attack']['events']
        self.assertEqual(len(events), 40)
        self.assertTrue(all(e['result'] == 'failure' and 'attempts' not in e for e in events))
        self.assertEqual(len({e['id'] for e in events}), 40)

    def test_detection_alerts_do_not_reveal_counts_or_success(self):
        for name in ('Possible compromise', 'Failed attack'):
            self.assertEqual(SCENARIOS[name]['alert'], 'Multiple failed logins within five minutes')
            from datetime import datetime
            failures = [e for e in SCENARIOS[name]['events'] if e.get('result') == 'failure']
            times = [datetime.fromisoformat(e['time'].replace('Z', '+00:00')) for e in failures]
            self.assertLess((max(times) - min(times)).total_seconds(), 300)
