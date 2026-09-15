"""Unit test verifying demo lifecycle, baseline R01/R02, and R03 evolution."""

import json
import unittest
from pathlib import Path
from tiltlock.config import AppConfig
from tiltlock.demo_runner import run_demo
from tiltlock.evolver import ChecklistEvolver


class TestDemoLifecycle(unittest.TestCase):
    def setUp(self):
        self.root = AppConfig.find_repo_root()
        self.checklist_path = self.root / "state" / "checklist.json"
        # Reset to baseline R01 and R02
        self.baseline_data = {
            "version": 1,
            "updated_at": "2026-09-11T12:00:00Z",
            "rules": [
                {
                    "rule_id": "R01",
                    "condition": "High-impact macro data releases (CPI, FOMC, NFP)",
                    "hard_constraint": "No new market or limit entries within 5 minutes before/after event",
                    "rationale": "Slippage spike and erratic spread expansion during high volatility events",
                    "created_at": "2026-09-11T12:00:00Z",
                },
                {
                    "rule_id": "R02",
                    "condition": "Tokenized equity (rToken) intraday trading",
                    "hard_constraint": "Maximum position sizing capped at 15 contracts per trade",
                    "rationale": "Prevents overleveraging in thin off-market order books",
                    "created_at": "2026-09-11T12:00:00Z",
                },
            ],
        }
        with open(self.checklist_path, "w", encoding="utf-8") as f:
            json.dump(self.baseline_data, f, indent=2)

    def tearDown(self):
        # Restore baseline for clean state
        with open(self.checklist_path, "w", encoding="utf-8") as f:
            json.dump(self.baseline_data, f, indent=2)

    def test_demo_resets_to_r01_r02_and_ends_with_r03(self):
        """Proves Task D: demo begins with R01/R02 and evolves to include R03."""
        evolver = ChecklistEvolver(self.checklist_path)
        initial = evolver.load_checklist()
        self.assertEqual(len(initial.rules), 2)
        self.assertEqual([r.rule_id for r in initial.rules], ["R01", "R02"])

        # Run demo with auto_yes=True and aggressive=True
        exit_code = run_demo(auto_yes=True, aggressive=True)
        self.assertEqual(exit_code, 0)

        # Verify post-demo state
        updated = evolver.load_checklist()
        rule_ids = [r.rule_id for r in updated.rules]
        self.assertIn("R01", rule_ids)
        self.assertIn("R02", rule_ids)
        self.assertIn("R03", rule_ids)
        self.assertEqual(len(updated.rules), 3)


if __name__ == "__main__":
    unittest.main()
