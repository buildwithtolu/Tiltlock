"""Unit tests for TiltDiagnostician."""

import unittest
from tiltlock.diagnostician import TiltDiagnostician, CANNED_DEMO_DIAGNOSIS
from tiltlock.models import TiltTriggerEvent, Checklist, EvolvedRule


class TestTiltDiagnostician(unittest.TestCase):
    def setUp(self):
        self.checklist = Checklist(
            version=1,
            rules=[
                EvolvedRule(
                    rule_id="R01",
                    condition="Macro news",
                    hard_constraint="No entry within 5m",
                    rationale="Spread spikes",
                ),
                EvolvedRule(
                    rule_id="R02",
                    condition="rToken sizing",
                    hard_constraint="Max position sizing 15 contracts",
                    rationale="Thin book protection",
                ),
            ],
        )

    def test_demo_mode_returns_canned_zero_network(self):
        diag_engine = TiltDiagnostician(mode="demo")
        trigger = TiltTriggerEvent(is_triggered=True, signatures=["SIZE_ESCALATION"])
        res = diag_engine.diagnose(trigger, self.checklist)

        self.assertEqual(res.pathology, CANNED_DEMO_DIAGNOSIS.pathology)
        self.assertEqual(res.confidence, CANNED_DEMO_DIAGNOSIS.confidence)
        self.assertIn("R02", res.violated_checklist_rules)
        self.assertLessEqual(len(res.sequence_audit.split()), 120)

    def test_fallback_produces_valid_schema(self):
        # Force fallback by passing invalid endpoint in paper mode
        diag_engine = TiltDiagnostician(mode="paper")
        diag_engine.config.policy.qwen_api_url = "http://127.0.0.1:9999/nonexistent"

        trigger = TiltTriggerEvent(
            is_triggered=True,
            signatures=["SIZE_ESCALATION"],
            size_ratio=2.5,
            session_loss=350.0,
            symbol="rTSLAUSDT",
        )
        res = diag_engine.diagnose(trigger, self.checklist)

        self.assertEqual(res.confidence, 0.0)
        self.assertTrue(len(res.evolved_rule.rule_id) >= 2)
        self.assertGreaterEqual(res.prescribed_cooldown_minutes, 15)
        self.assertLessEqual(res.prescribed_cooldown_minutes, 120)


if __name__ == "__main__":
    unittest.main()
