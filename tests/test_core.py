import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from soc.core import investigate, load_runs
from soc.data import SCENARIOS

class InvestigationTests(unittest.TestCase):
    def run_fake(self, response=None, error=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.sqlite3"
            with patch("soc.core.httpx.Client") as client:
                post = client.return_value.__enter__.return_value.post
                if error:
                    post.side_effect = error
                else:
                    post.return_value = httpx.Response(200, json=response, request=httpx.Request("POST", "http://localhost/api/chat"))
                run = investigate("Investigate", SCENARIOS["Failed attack"], "test", "http://localhost", path=path)
            self.assertEqual(load_runs(path)[0]["id"], run["id"])
            return run

    def body(self, ids):
        return {"message": {"content": json.dumps({"summary": "Failed attempts", "findings": [{"claim": "Failed logins", "evidence_ids": ids}], "uncertainty": ["Incomplete window"], "next_steps": ["Check subsequent events"]})}, "eval_count": 20, "eval_duration": 2_000_000_000}

    def test_valid_result_and_throughput(self):
        run = self.run_fake(self.body(["e1"]))
        self.assertEqual(run["status"], "ok")
        self.assertEqual(run["metrics"]["tokens_per_second"], 10)

    def test_hallucinated_reference_is_flagged(self):
        run = self.run_fake(self.body(["invented"]))
        self.assertEqual(run["status"], "citation_warning")
        self.assertEqual(run["checks"]["unknown_evidence_ids"], ["invented"])

    def test_invalid_schema_is_saved(self):
        run = self.run_fake({"message": {"content": '{"summary": "only"}'}})
        self.assertEqual(run["status"], "error")
        self.assertFalse(run["schema_valid"])

    def test_timeout_is_saved_without_fake_usage(self):
        run = self.run_fake(error=httpx.ReadTimeout("Timed out"))
        self.assertEqual(run["status"], "error")
        self.assertIsNone(run["metrics"]["eval_count"])

class RequestTests(unittest.TestCase):
    def test_history_and_explicit_budget(self):
        from soc.core import build_request, estimate_context
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(12)]
        request = build_request("Follow up", SCENARIOS["Failed attack"], "test", history, 8192, 512)
        self.assertEqual(request["options"]["num_ctx"], 8192)
        self.assertEqual(request["options"]["num_predict"], 512)
        self.assertEqual(request["messages"][2:-1], history[-8:])
        self.assertEqual(request["messages"][-1]["content"], "Follow up")
        rows = estimate_context(request)
        self.assertEqual([row["section"] for row in rows[:2]], ["System", "Evidence"])
        self.assertEqual(rows[-1]["section"], "Question")

    def test_invalid_budget(self):
        from soc.core import build_request
        with self.assertRaises(ValueError):
            build_request("test", SCENARIOS["Failed attack"], "test", num_ctx=512, num_predict=512)

    def test_sampling_settings_and_optional_seed(self):
        from soc.core import build_request
        args = ('test', SCENARIOS['Failed attack'], 'test')
        self.assertNotIn('seed', build_request(*args)['options'])
        options = build_request(*args, temperature=0.7, top_p=0.8, top_k=20, repeat_penalty=1.2, seed=42)['options']
        self.assertEqual({k: options[k] for k in ('temperature', 'top_p', 'top_k', 'repeat_penalty', 'seed')},
                         dict(temperature=0.7, top_p=0.8, top_k=20, repeat_penalty=1.2, seed=42))
