"""Signal client fail-open tests."""

import unittest
from unittest.mock import patch
from tiltlock.signals import fetch_sentiment_snapshot, _fear_greed_label


class TestSignals(unittest.TestCase):
    def test_fear_greed_labels(self):
        self.assertEqual(_fear_greed_label(10), "Extreme Fear")
        self.assertEqual(_fear_greed_label(50), "Neutral")
        self.assertEqual(_fear_greed_label(90), "Extreme Greed")

    @patch("tiltlock.signals.requests.Session")
    def test_timeout_does_not_raise(self, mock_session_cls):
        mock_session_cls.return_value.post.side_effect = TimeoutError("slow")
        result = fetch_sentiment_snapshot(timeout_sec=0.1)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("bitget-signal", result["source"])

    def test_review_includes_signal_summary(self):
        from tiltlock.diagnostician import TiltDiagnostician
        from tiltlock.models import TiltTriggerEvent, Checklist, EvolvedRule

        engine = TiltDiagnostician()
        trigger = TiltTriggerEvent(
            is_triggered=True,
            signatures=["SIZE_ESCALATION"],
            size_ratio=2.5,
            session_loss=200.0,
            symbol="rTSLAUSDT",
            summary="SIZE_ESCALATION",
        )
        checklist = Checklist(
            rules=[
                EvolvedRule(
                    rule_id="R02",
                    condition="size",
                    hard_constraint="Maximum position sizing capped",
                    rationale="x",
                )
            ]
        )
        res = engine.diagnose(
            trigger,
            checklist,
            market_context={
                "source": "bitget-signal:sentiment-analyst",
                "summary": "Fear & Greed 24 (Extreme Fear)",
            },
        )
        self.assertIn("bitget-signal", res.sequence_audit)
        self.assertIn("24", res.sequence_audit)


if __name__ == "__main__":
    unittest.main()
