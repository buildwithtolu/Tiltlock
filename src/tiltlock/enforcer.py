"""Enforcement layer mediating Bitget Agent Hub actions and local cooldown gate."""

import json
import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from tiltlock.config import get_config, AppConfig
from tiltlock.models import LockState

logger = logging.getLogger("tiltlock.enforcer")


def resolve_bgc_prefix() -> Optional[List[str]]:
    """Return argv prefix that can launch bgc under Windows and Unix.

    npm installs `bgc` as `.cmd` / `.ps1` shims on Windows. Python's
    subprocess cannot reliably execute the bare shim name, which surfaces as
    WinError 2. Prefer `node <cli entry>` or an absolute `bgc.cmd` path.
    """
    node = shutil.which("node")
    appdata = os.environ.get("APPDATA", "")
    npm_root = Path(appdata) / "npm" if appdata else None

    if npm_root is not None:
        entry = (
            npm_root
            / "node_modules"
            / "@bitget-ai"
            / "bitget-agent-cli"
            / "lib"
            / "index.js"
        )
        if node and entry.exists():
            return [node, str(entry)]
        cmd_shim = npm_root / "bgc.cmd"
        if cmd_shim.exists():
            return [str(cmd_shim)]

    which = shutil.which("bgc")
    if not which:
        return None

    path = Path(which)
    if sys.platform == "win32":
        if path.suffix.lower() == ".ps1":
            cmd_sibling = path.with_suffix(".cmd")
            if cmd_sibling.exists():
                return [str(cmd_sibling)]
        if path.suffix.lower() in {".cmd", ".bat"}:
            return [str(path)]
        cmd_sibling = path.parent / "bgc.cmd"
        if cmd_sibling.exists():
            return [str(cmd_sibling)]

    return [which]


class BitgetClient(ABC):
    """Abstract adapter defining the realistic Bitget Agent Hub surface."""

    @abstractmethod
    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[str]:
        """Cancels all active regular limit/market orders."""
        pass

    @abstractmethod
    def cancel_strategy_orders(self, symbol: Optional[str] = None) -> List[str]:
        """Lists open plan/trigger/SL orders and cancels each individually."""
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int = 1) -> bool:
        """Resets sub-account leverage to 1x to contain risk."""
        pass

    @abstractmethod
    def close_position(self, symbol: Optional[str] = None) -> bool:
        """Closes position if aggressive flatten policy is enabled."""
        pass

    def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> Dict[str, Any]:
        """Shared gateway middleware: checks cooldown lock before routing order."""
        is_locked, state = self.check_lock()
        if is_locked:
            unlocks_at = state.unlocks_at if state else "unknown"
            reason = state.reason if state else "Cooldown active"
            logger.debug(
                "Order placement blocked: PERMISSION_DENIED_COOLDOWN_ACTIVE (until %s)",
                unlocks_at,
            )
            raise PermissionError(
                f"PERMISSION_DENIED_COOLDOWN_ACTIVE: Account in cooldown until {unlocks_at}. Reason: {reason}"
            )
        return self._do_place_order(symbol, side, size, price, order_type)

    @abstractmethod
    def _do_place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> Dict[str, Any]:
        """Underlying order placement implementation."""
        pass

    def set_cooldown(
        self, minutes: int, reason: str, session_cost: float = 0.0
    ) -> LockState:
        """Enforces a local gateway freeze by writing lockfile state."""
        root = AppConfig.find_repo_root()
        lock_file = root / "state" / "lock_state.json"
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.utcnow()
        unlock_time = now + timedelta(minutes=minutes)

        state = LockState(
            is_locked=True,
            locked_at=now.isoformat() + "Z",
            unlocks_at=unlock_time.isoformat() + "Z",
            reason=reason,
            cooldown_minutes=minutes,
            session_cost=session_cost,
        )

        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))

        return state

    def check_lock(self) -> Tuple[bool, Optional[LockState]]:
        """Checks if account is currently in cooldown."""
        root = AppConfig.find_repo_root()
        lock_file = root / "state" / "lock_state.json"
        if not lock_file.exists():
            return False, None

        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = LockState(**data)

            if not state.is_locked:
                return False, state

            if state.unlocks_at:
                unlock_dt = datetime.fromisoformat(state.unlocks_at.rstrip("Z"))
                if datetime.utcnow() >= unlock_dt:
                    # Expired
                    state.is_locked = False
                    with open(lock_file, "w", encoding="utf-8") as f:
                        f.write(state.model_dump_json(indent=2))
                    return False, state

            return True, state
        except Exception:
            return False, None

    def clear_lock(self) -> LockState:
        """Clears local cooldown lockfile."""
        root = AppConfig.find_repo_root()
        lock_file = root / "state" / "lock_state.json"
        state = LockState(is_locked=False)
        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(state.model_dump_json(indent=2))
        return state


class MockBitgetClient(BitgetClient):
    """Deterministic, zero-network mock client for --demo and unit tests."""

    def __init__(self):
        self.canceled_orders: List[str] = []
        self.canceled_strategy_orders: List[str] = []
        self.leverage_settings: dict = {}
        self.positions_closed: List[str] = []
        self.placed_orders: List[dict] = []

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[str]:
        target = f"ALL_REGULAR_ORDERS({symbol or 'ALL_SYMBOLS'})"
        self.canceled_orders.append(target)
        return [target]

    def cancel_strategy_orders(self, symbol: Optional[str] = None) -> List[str]:
        # Demo-only stand-ins for resting stop/trigger orders.
        demo_strategy_orders = [
            f"DEMO-SL-{symbol or 'TSLAUSDT'}",
            f"DEMO-TP-{symbol or 'TSLAUSDT'}",
        ]
        canceled = []
        for strat_id in demo_strategy_orders:
            self.canceled_strategy_orders.append(strat_id)
            canceled.append(strat_id)
        return canceled

    def set_leverage(self, symbol: str, leverage: int = 1) -> bool:
        self.leverage_settings[symbol] = leverage
        return True

    def close_position(self, symbol: Optional[str] = None) -> bool:
        sym = symbol or "ALL_POSITIONS"
        self.positions_closed.append(sym)
        return True

    def _do_place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> Dict[str, Any]:
        order_id = f"MOCK-ORD-{symbol}-{len(self.placed_orders)+1}"
        record = {
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "size": size,
            "price": price,
            "type": order_type,
            "status": "PLACED",
        }
        self.placed_orders.append(record)
        return record


class BgcCliBitgetClient(BitgetClient):
    """Executes Bitget Agent Hub CLI commands for Demo Trading (--paper).

    Destructive writes require allow_writes=True. Production/live mode is not
    exposed through the public CLI factory.
    """

    def __init__(self, paper_mode: bool = True, allow_writes: bool = False):
        if not paper_mode:
            raise RuntimeError(
                "Live/production Bitget mode is disabled in TiltLock. "
                "Use paper_mode=True with Demo API keys, or run --demo."
            )
        self.paper_mode = True
        self.allow_writes = allow_writes
        self.base_flags = ["--paper-trading"]

    @staticmethod
    def is_bgc_installed() -> bool:
        """Checks if bgc can be resolved to a runnable Windows/Unix command."""
        return resolve_bgc_prefix() is not None

    @classmethod
    def probe(cls, paper_mode: bool = True) -> Tuple[bool, str, str]:
        """Probes whether bgc is runnable and authenticated for paper trading.

        Returns:
            (is_ready, status_code, message)
            status_code in {"OK", "BINARY_NOT_FOUND", "AUTH_FAILED"}
        """
        prefix = resolve_bgc_prefix()
        if not prefix:
            return (
                False,
                "BINARY_NOT_FOUND",
                "Bitget Agent Hub CLI ('bgc') is not installed or not found on PATH.",
            )

        base_flags = ["--paper-trading"] if paper_mode else []
        cmd = prefix + ["discover"] + base_flags
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip() or "Unauthenticated session"
                return (
                    False,
                    "AUTH_FAILED",
                    f"bgc probe exited with code {res.returncode}: {err_msg}",
                )
            return True, "OK", "bgc paper session active and authenticated."
        except Exception as e:
            return False, "AUTH_FAILED", f"bgc execution error: {str(e)}"

    def _require_writes(self, action: str) -> None:
        if not self.allow_writes:
            raise PermissionError(
                f"WRITE_BLOCKED: '{action}' needs explicit consent. "
                "Re-run with --yes or --i-understand (Demo Trading only)."
            )

    def _run_bgc(self, args: List[str]) -> Tuple[int, str]:
        prefix = resolve_bgc_prefix()
        if not prefix:
            return 127, "bgc not found"
        cmd = prefix + args + self.base_flags
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return res.returncode, res.stdout + res.stderr

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[str]:
        self._require_writes("order cancelAll")
        args = ["order", "--action", "cancelAll", "--confirm"]
        if symbol:
            args.extend(["--symbol", symbol])
        code, out = self._run_bgc(args)
        return [f"order cancelAll: {out.strip()}"]

    def cancel_strategy_orders(self, symbol: Optional[str] = None) -> List[str]:
        self._require_writes("strategy_order cancel")
        list_args = ["strategy_order", "--action", "open"]
        if symbol:
            list_args.extend(["--symbol", symbol])

        code, out = self._run_bgc(list_args)
        canceled = []
        try:
            data = json.loads(out)
            items = data if isinstance(data, list) else data.get("data", [])
            if isinstance(items, dict):
                items = items.get("list", []) or items.get("orders", [])
            for item in items or []:
                order_id = item.get("orderId") or item.get("id")
                if order_id:
                    self._run_bgc(
                        [
                            "strategy_order",
                            "--action",
                            "cancel",
                            "--orderId",
                            str(order_id),
                            "--confirm",
                        ]
                    )
                    canceled.append(str(order_id))
        except Exception:
            canceled.append("strategy_order_open_and_cancel_executed")

        return canceled

    def set_leverage(self, symbol: str, leverage: int = 1) -> bool:
        self._require_writes("position setLeverage")
        args = [
            "position",
            "--action",
            "setLeverage",
            "--symbol",
            symbol,
            "--leverage",
            str(leverage),
        ]
        code, _ = self._run_bgc(args)
        return code == 0

    def close_position(self, symbol: Optional[str] = None) -> bool:
        self._require_writes("position close")
        if symbol:
            args = ["position", "--action", "close", "--symbol", symbol, "--confirm"]
        else:
            args = ["position", "--action", "closeAll", "--confirm"]
        code, _ = self._run_bgc(args)
        return code == 0

    def _do_place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        price: Optional[float] = None,
        order_type: str = "LIMIT",
    ) -> Dict[str, Any]:
        self._require_writes("order place")
        args = [
            "order",
            "--action",
            "place",
            "--symbol",
            symbol,
            "--side",
            side.lower(),
            "--size",
            str(size),
            "--type",
            order_type.lower(),
            "--confirm",
        ]
        if price is not None:
            args.extend(["--price", str(price)])
        code, out = self._run_bgc(args)
        return {"output": out, "status": "SUBMITTED" if code == 0 else "FAILED"}

    def get_recent_fills(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Polls recent order fills via bgc."""
        args = ["order", "--action", "fills"]
        if symbol:
            args.extend(["--symbol", symbol])
        code, out = self._run_bgc(args)
        if code != 0:
            return []
        try:
            data = json.loads(out)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("list", []) or data.get("fills", []) or data.get("data", []) or []
        except Exception:
            pass
        return []

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Polls current open orders via bgc."""
        args = ["order", "--action", "open"]
        if symbol:
            args.extend(["--symbol", symbol])
        code, out = self._run_bgc(args)
        if code != 0:
            return []
        try:
            data = json.loads(out)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("list", []) or data.get("orders", []) or data.get("data", []) or []
        except Exception:
            pass
        return []


def get_bitget_client(mode: str = "demo", allow_writes: bool = False) -> BitgetClient:
    """Factory for supported clients. Live/production mode is intentionally unavailable."""
    if mode == "demo":
        return MockBitgetClient()
    if mode == "paper":
        return BgcCliBitgetClient(paper_mode=True, allow_writes=allow_writes)
    if mode == "live":
        raise RuntimeError(
            "Live/production mode is disabled. Use --demo or --paper with Demo API keys."
        )
    return MockBitgetClient()
