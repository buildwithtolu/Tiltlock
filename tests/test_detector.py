"""Unit tests for TiltDetector."""

import unittest
from tiltlock.detector import TiltDetector
from tiltlock.models import TradeFill, OrderCancel


class TestTiltDetector(unittest.TestCase):
    def setUp(self):
        self.detector = TiltDetector(baseline_size=10.0)

    def test_loss_streak_trigger(self):
        # Ingest 3 consecutive losing trades
        t1 = self.detector.ingest_fill(
            TradeFill(order_id="1", symbol="BTC", side="BUY", size=10, pnl=-50, timestamp_offset_sec=10)
        )
        self.assertFalse(t1.is_triggered)
        self.assertEqual(t1.loss_streak, 1)

        t2 = self.detector.ingest_fill(
            TradeFill(order_id="2", symbol="BTC", side="BUY", size=10, pnl=-50, timestamp_offset_sec=20)
        )
        self.assertFalse(t2.is_triggered)
        self.assertEqual(t2.loss_streak, 2)

        t3 = self.detector.ingest_fill(
            TradeFill(order_id="3", symbol="BTC", side="BUY", size=10, pnl=-50, timestamp_offset_sec=30)
        )
        self.assertTrue(t3.is_triggered)
        self.assertEqual(t3.loss_streak, 3)
        self.assertTrue(any("LOSS_STREAK" in s for s in t3.signatures))

    def test_rapid_reentry_with_size_escalation(self):
        # Stop loss exit
        self.detector.ingest_fill(
            TradeFill(
                order_id="1",
                symbol="TSLA",
                side="SELL",
                size=10,
                pnl=-100,
                exit_reason="STOP_LOSS",
                timestamp_offset_sec=0,
            )
        )
        # Re-entry 35s later with 2.5x size (25 contracts vs 10 baseline)
        t2 = self.detector.ingest_fill(
            TradeFill(
                order_id="2",
                symbol="TSLA",
                side="BUY",
                size=25,
                pnl=0,
                timestamp_offset_sec=35,
            )
        )
        self.assertTrue(t2.is_triggered)
        self.assertTrue(any("RAPID_REENTRY" in s for s in t2.signatures))
        self.assertTrue(any("SIZE_ESCALATION" in s for s in t2.signatures))

    def test_stop_loss_tamper_in_drawdown(self):
        # Cancel order while in drawdown
        t_cancel = self.detector.ingest_cancel(
            OrderCancel(
                order_id="SL-1",
                symbol="NVDA",
                side="SELL",
                price=120.0,
                unrealized_pnl=-85.0,
                timestamp_offset_sec=50,
            )
        )
        self.assertTrue(t_cancel.is_triggered)
        self.assertTrue(t_cancel.sl_tampered)
        self.assertTrue(any("STOP_LOSS_TAMPER" in s for s in t_cancel.signatures))


if __name__ == "__main__":
    unittest.main()
