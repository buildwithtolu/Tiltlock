"""Unit tests verifying paper mode probe, polling, and bgc error handling."""

import json
import unittest
from unittest.mock import MagicMock, patch
from tiltlock.config import AppConfig
from tiltlock.enforcer import BgcCliBitgetClient
from tiltlock.evolver import ChecklistEvolver
from tiltlock.paper_runner import run_paper, normalize_bgc_fill, normalize_bgc_cancel


class TestPaperMode(unittest.TestCase):
    def setUp(self):
        self.root = AppConfig.find_repo_root()
        self.checklist_path = self.root / "state" / "checklist.json"
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
        with open(self.checklist_path, "w", encoding="utf-8") as f:
            json.dump(self.baseline_data, f, indent=2)
        client = BgcCliBitgetClient(paper_mode=True)
        client.clear_lock()

    @patch("tiltlock.enforcer.resolve_bgc_prefix", return_value=None)
    def test_probe_fails_when_bgc_missing(self, _mock_prefix):
        """Proves Task A & D: probe fails and run_paper exits 1 when bgc binary is missing."""
        ok, code, msg = BgcCliBitgetClient.probe(paper_mode=True)
        self.assertFalse(ok)
        self.assertEqual(code, "BINARY_NOT_FOUND")

        exit_code = run_paper(auto_yes=True)
        self.assertEqual(exit_code, 1)

    @patch("subprocess.run")
    @patch(
        "tiltlock.enforcer.resolve_bgc_prefix",
        return_value=["bgc"],
    )
    def test_probe_fails_when_auth_failed(self, _mock_prefix, mock_subproc):
        """Proves Task A: probe fails and run_paper exits 1 when bgc discover fails auth."""
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "Session unauthenticated or expired"
        mock_res.stdout = ""
        mock_subproc.return_value = mock_res

        ok, code, msg = BgcCliBitgetClient.probe(paper_mode=True)
        self.assertFalse(ok)
        self.assertEqual(code, "AUTH_FAILED")

        exit_code = run_paper(auto_yes=True)
        self.assertEqual(exit_code, 1)

    @patch("subprocess.run")
    @patch(
        "tiltlock.enforcer.resolve_bgc_prefix",
        return_value=["bgc"],
    )
    def test_probe_ok_when_discover_succeeds(self, _mock_prefix, mock_subproc):
        """Proves Task A: probe passes when bgc discover succeeds."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "OK"
        mock_res.stderr = ""
        mock_subproc.return_value = mock_res

        ok, code, msg = BgcCliBitgetClient.probe(paper_mode=True)
        self.assertTrue(ok)
        self.assertEqual(code, "OK")

    @patch("subprocess.run")
    @patch("tiltlock.enforcer.BgcCliBitgetClient.probe", return_value=(True, "OK", "Active"))
    def test_paper_fixture_replay_enforces_and_blocks_order(self, mock_probe, mock_subproc):
        """Proves Task B & D: run --paper --fixture executes enforcement via BgcCliBitgetClient."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = json.dumps([{"orderId": "STRAT-999"}])
        mock_res.stderr = ""
        mock_subproc.return_value = mock_res

        exit_code = run_paper(auto_yes=True, aggressive=True, use_fixture=True, use_signal=False)
        self.assertEqual(exit_code, 0)

        # Verify enforcement calls constructed
        all_calls = [call[0][0] for call in mock_subproc.call_args_list]
        cancel_all_called = any("cancelAll" in cmd for cmd in all_calls)
        set_leverage_called = any("setLeverage" in cmd for cmd in all_calls)
        close_called = any("close" in cmd for cmd in all_calls)

        self.assertTrue(cancel_all_called)
        self.assertTrue(set_leverage_called)
        self.assertTrue(close_called)

    @patch("subprocess.run")
    @patch("tiltlock.enforcer.BgcCliBitgetClient.probe", return_value=(True, "OK", "Active"))
    def test_paper_polling_loop_triggers_enforcement(self, mock_probe, mock_subproc):
        """Proves Task B & D: live polling loop ingests fills and triggers enforcement on tilt."""
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = json.dumps([
            {"orderId": "ORD-1", "symbol": "rTSLAUSDT", "side": "BUY", "size": 10, "pnl": -100.0, "exitReason": "STOP_LOSS"},
            {"orderId": "ORD-2", "symbol": "rTSLAUSDT", "side": "BUY", "size": 10, "pnl": -100.0},
            {"orderId": "ORD-3", "symbol": "rTSLAUSDT", "side": "BUY", "size": 10, "pnl": -100.0},
        ])
        mock_res.stderr = ""
        mock_subproc.return_value = mock_res

        # Run 1 poll cycle
        exit_code = run_paper(
            auto_yes=True, aggressive=False, use_fixture=False, poll_override=1, use_signal=False
        )
        self.assertEqual(exit_code, 0)

        all_calls = [call[0][0] for call in mock_subproc.call_args_list]
        cancel_all_called = any("cancelAll" in cmd for cmd in all_calls)
        set_leverage_called = any("setLeverage" in cmd for cmd in all_calls)
        self.assertTrue(cancel_all_called)
        self.assertTrue(set_leverage_called)

    def test_locked_gateway_blocks_place_order_during_paper(self):
        """Proves Task D(3): locked gateway blocks place_order during paper enforcement."""
        client = BgcCliBitgetClient(paper_mode=True)
        client.set_cooldown(minutes=30, reason="TILT_DETECTED", session_cost=300.0)

        with self.assertRaises(PermissionError) as ctx:
            client.place_order("rTSLAUSDT", "BUY", 10.0, 240.0)
        self.assertIn("PERMISSION_DENIED_COOLDOWN_ACTIVE", str(ctx.exception))

        # Clear lock allows order to proceed to bgc invocation
        client.clear_lock()
        with patch.object(client, "_do_place_order", return_value={"status": "SUBMITTED"}) as mock_do:
            res = client.place_order("rTSLAUSDT", "BUY", 10.0, 240.0)
            mock_do.assert_called_once()
            self.assertEqual(res["status"], "SUBMITTED")

    def test_normalize_bgc_fill_and_cancel(self):
        raw_fill = {
            "orderId": "FILL-1234",
            "symbol": "rNVDAUSDT",
            "side": "buy",
            "size": "15",
            "price": "125.5",
            "pnl": "-50.0",
            "exitReason": "STOP_LOSS",
        }
        fill = normalize_bgc_fill(raw_fill, timestamp_offset_sec=10)
        self.assertEqual(fill.order_id, "FILL-1234")
        self.assertEqual(fill.symbol, "rNVDAUSDT")
        self.assertEqual(fill.side, "BUY")
        self.assertEqual(fill.size, 15.0)
        self.assertEqual(fill.pnl, -50.0)
        self.assertEqual(fill.exit_reason, "STOP_LOSS")

        raw_cancel = {
            "orderId": "CANCEL-5678",
            "symbol": "rTSLAUSDT",
            "side": "sell",
            "price": "239.50",
            "unrealizedPnl": "-120.0",
        }
        cancel = normalize_bgc_cancel(raw_cancel, timestamp_offset_sec=15)
        self.assertEqual(cancel.order_id, "CANCEL-5678")
        self.assertEqual(cancel.symbol, "rTSLAUSDT")
        self.assertEqual(cancel.side, "SELL")
        self.assertEqual(cancel.price, 239.50)
        self.assertEqual(cancel.unrealized_pnl, -120.0)


if __name__ == "__main__":
    unittest.main()
