"""Unit tests for TiltDiagnostician."""

import unittest
from tiltlock.diagnostician import TiltDiagnostician
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

    def test_demo_review_uses_trigger_fields(self):
        diag_engine = TiltDiagnostician(mode="demo")
        trigger = TiltTriggerEvent(
            is_triggered=True,
            signatures=["SIZE_ESCALATION (2.5x baseline)", "STOP_LOSS_TAMPER (SL canceled while in drawdown)"],
            size_ratio=2.5,
            session_loss=550.0,
            sl_tampered=True,
            seconds_since_last_stop=38,
            symbol="rTSLAUSDT",
            summary="SIZE_ESCALATION (2.5x baseline), STOP_LOSS_TAMPER",
        )
        res = diag_engine.diagnose(trigger, self.checklist)
        self.assertEqual(res.pathology, "SUNK_COST_ESCALATION")
        self.assertIn("rTSLAUSDT", res.sequence_audit)
        self.assertIn("550", res.sequence_audit)
        self.assertIn("R02", res.violated_checklist_rules)
        self.assertLessEqual(len(res.sequence_audit.split()), 120)

    def test_changing_session_loss_changes_review(self):
        engine = TiltDiagnostician(mode="demo")
        a = engine.diagnose(
            TiltTriggerEvent(
                is_triggered=True,
                signatures=["RAPID_REENTRY"],
                session_loss=100.0,
                symbol="rNVDAUSDT",
                size_ratio=1.0,
            ),
            self.checklist,
        )
        b = engine.diagnose(
            TiltTriggerEvent(
                is_triggered=True,
                signatures=["RAPID_REENTRY"],
                session_loss=999.0,
                symbol="rNVDAUSDT",
                size_ratio=1.0,
            ),
            self.checklist,
        )
        self.assertNotEqual(a.sequence_audit, b.sequence_audit)
        self.assertIn("999", b.sequence_audit)

    def test_paper_without_qwen_key_uses_local_review(self):
        diag_engine = TiltDiagnostician(mode="paper", live_llm=True)
        diag_engine.config.policy.qwen_api_url = "http://127.0.0.1:9999/nonexistent"
        trigger = TiltTriggerEvent(
            is_triggered=True,
            signatures=["SIZE_ESCALATION"],
            size_ratio=2.5,
            session_loss=350.0,
            symbol="rTSLAUSDT",
        )
        res = diag_engine.diagnose(trigger, self.checklist)
        self.assertIn("rTSLAUSDT", res.sequence_audit)
        self.assertGreaterEqual(res.prescribed_cooldown_minutes, 15)
        self.assertLessEqual(res.prescribed_cooldown_minutes, 120)


if __name__ == "__main__":
    unittest.main()
