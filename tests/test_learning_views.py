import json
import unittest
from soc.inspector import final_evidence


class LearningEvidenceTests(unittest.TestCase):
    def test_uses_final_input_instead_of_collected_metadata(self):
        run = {"evidence_collected": {"events": [{"id": "excluded"}]},
               "request": {"messages": [{}, {"content": "Evidence:\n" + json.dumps({"events": [{"id": "included"}]})}]}}
        self.assertEqual(final_evidence(run)["events"][0]["id"], "included")

    def test_failed_gathering_and_legacy_missing_input(self):
        self.assertEqual(final_evidence({}), {})
        self.assertEqual(final_evidence({"request": {"messages": [{}, {"content": "Alert metadata:\n{}"}]}}), {})


class StageInstructionTests(unittest.TestCase):
    def test_stage_instructions_are_distinct(self):
        from soc.core import GATHER_SYSTEM, FINAL_SYSTEM, build_request
        from soc.data import SCENARIOS
        self.assertIn("Use the supplied tools", GATHER_SYSTEM)
        self.assertNotIn("No tools are available", GATHER_SYSTEM)
        self.assertNotIn("required JSON schema", GATHER_SYSTEM)
        self.assertIn("No tools are available during this stage", FINAL_SYSTEM)
        request = build_request("Investigate", SCENARIOS["Failed attack"], "test")
        self.assertEqual(request["messages"][0]["content"], FINAL_SYSTEM)
