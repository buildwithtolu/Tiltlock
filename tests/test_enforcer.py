"""Unit tests for enforcer, BitgetClient adapter, and order gateway middleware."""

import json
import unittest
from unittest.mock import MagicMock, patch
from tiltlock.enforcer import MockBitgetClient, BgcCliBitgetClient


class TestEnforcer(unittest.TestCase):
    def setUp(self):
        self.client = MockBitgetClient()
        self.client.clear_lock()

    def test_mock_enforcement_actions(self):
        orders = self.client.cancel_all_orders("TSLAUSDT_rToken")
        self.assertTrue(len(orders) > 0)
        self.assertTrue(len(self.client.canceled_orders) > 0)

        # strategy_order list and cancel individually
        strategies = self.client.cancel_strategy_orders("TSLAUSDT_rToken")
        self.assertTrue(len(strategies) >= 2)
        self.assertEqual(len(self.client.canceled_strategy_orders), len(strategies))

        # Leverage change
        res = self.client.set_leverage("TSLAUSDT_rToken", leverage=1)
        self.assertTrue(res)
        self.assertEqual(self.client.leverage_settings.get("TSLAUSDT_rToken"), 1)

    def test_lock_state_lifecycle(self):
        state = self.client.set_cooldown(minutes=30, reason="TEST_TILT", session_cost=200.0)
        self.assertTrue(state.is_locked)
        self.assertEqual(state.cooldown_minutes, 30)

        is_locked, current = self.client.check_lock()
        self.assertTrue(is_locked)
        self.assertIsNotNone(current)
        self.assertEqual(current.reason, "TEST_TILT")

        cleared = self.client.clear_lock()
        self.assertFalse(cleared.is_locked)

        is_locked, _ = self.client.check_lock()
        self.assertFalse(is_locked)

    def test_locked_gateway_blocks_order_placement(self):
        """Proves Task B: check_lock blocks entry intent during active cooldown."""
        # 1. When unlocked, order placement succeeds
        self.client.clear_lock()
        res = self.client.place_order("TSLAUSDT_rToken", "BUY", 10.0, 240.0)
        self.assertEqual(res["status"], "PLACED")
        self.assertEqual(len(self.client.placed_orders), 1)

        # 2. When cooldown is set, order placement must raise PermissionError with exact message
        self.client.set_cooldown(minutes=45, reason="LOSS_STREAK_ESCALATION", session_cost=550.0)
        with self.assertRaises(PermissionError) as ctx:
            self.client.place_order("TSLAUSDT_rToken", "BUY", 25.0, 238.0)
        self.assertIn("PERMISSION_DENIED_COOLDOWN_ACTIVE", str(ctx.exception))

        # 3. Clearing lock immediately re-enables order placement
        self.client.clear_lock()
        res2 = self.client.place_order("TSLAUSDT_rToken", "BUY", 10.0, 241.0)
        self.assertEqual(res2["status"], "PLACED")
        self.assertEqual(len(self.client.placed_orders), 2)

    @patch("tiltlock.enforcer.resolve_bgc_prefix", return_value=["bgc"])
    @patch("subprocess.run")
    def test_paper_client_bgc_args(self, mock_subproc, _mock_prefix):
        """Proves Task D: BgcCliBitgetClient constructs correct authentic bgc arg lists."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "MOCK_SUCCESS"
        mock_res.stderr = ""
        mock_subproc.return_value = mock_res

        paper_client = BgcCliBitgetClient(paper_mode=True)

        # 1. cancel_all_orders
        paper_client.cancel_all_orders("TSLAUSDT_rToken")
        mock_subproc.assert_called_with(
            ["bgc", "order", "--action", "cancelAll", "--confirm", "--symbol", "TSLAUSDT_rToken", "--paper-trading"],
            capture_output=True,
            text=True,
            check=False,
        )

        # 2. cancel_strategy_orders queries open orders, then cancels
        mock_subproc.reset_mock()
        mock_res.stdout = json.dumps([{"orderId": "STRAT-999"}])
        paper_client.cancel_strategy_orders("TSLAUSDT_rToken")
        self.assertEqual(mock_subproc.call_count, 2)
        # First call: open strategy list
        self.assertEqual(
            mock_subproc.call_args_list[0][0][0],
            ["bgc", "strategy_order", "--action", "open", "--symbol", "TSLAUSDT_rToken", "--paper-trading"],
        )
        # Second call: cancel specific orderId
        self.assertEqual(
            mock_subproc.call_args_list[1][0][0],
            ["bgc", "strategy_order", "--action", "cancel", "--orderId", "STRAT-999", "--confirm", "--paper-trading"],
        )

        # 3. set_leverage
        mock_subproc.reset_mock()
        paper_client.set_leverage("TSLAUSDT_rToken", leverage=1)
        mock_subproc.assert_called_with(
            ["bgc", "position", "--action", "setLeverage", "--symbol", "TSLAUSDT_rToken", "--leverage", "1", "--paper-trading"],
            capture_output=True,
            text=True,
            check=False,
        )

        # 4. close_position
        mock_subproc.reset_mock()
        paper_client.close_position("TSLAUSDT_rToken")
        mock_subproc.assert_called_with(
            ["bgc", "position", "--action", "close", "--symbol", "TSLAUSDT_rToken", "--confirm", "--paper-trading"],
            capture_output=True,
            text=True,
            check=False,
        )

        # 5. place_order (unlocked)
        mock_subproc.reset_mock()
        paper_client.clear_lock()
        paper_client.place_order("TSLAUSDT_rToken", "BUY", 10.0, 240.0, order_type="LIMIT")
        mock_subproc.assert_called_with(
            ["bgc", "order", "--action", "place", "--symbol", "TSLAUSDT_rToken", "--side", "buy", "--size", "10.0", "--type", "limit", "--confirm", "--price", "240.0", "--paper-trading"],
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
