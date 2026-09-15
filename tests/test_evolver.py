"""Unit tests for ChecklistEvolver."""

import tempfile
import unittest
from pathlib import Path
from tiltlock.evolver import ChecklistEvolver
from tiltlock.models import EvolvedRule


class TestChecklistEvolver(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.checklist_path = Path(self.temp_dir.name) / "checklist.json"
        self.evolver = ChecklistEvolver(checklist_path=self.checklist_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_and_evolve_checklist(self):
        initial = self.evolver.load_checklist()
        self.assertEqual(initial.version, 1)
        self.assertEqual(len(initial.rules), 2)

        new_rule = EvolvedRule(
            rule_id="R03",
            condition="Post stop-loss",
            hard_constraint="30-minute lockout on same sector",
            rationale="Prevent revenge escalation",
        )

        accepted, updated = self.evolver.evaluate_rule_proposal(
            new_rule, auto_accept_seconds=0, auto_yes=True
        )

        self.assertTrue(accepted)
        self.assertEqual(updated.version, 2)
        self.assertEqual(len(updated.rules), 3)
        self.assertEqual(updated.rules[-1].rule_id, "R03")

        # Verify disk reload
        reloaded = self.evolver.load_checklist()
        self.assertEqual(reloaded.version, 2)
        self.assertEqual(len(reloaded.rules), 3)


if __name__ == "__main__":
    unittest.main()
