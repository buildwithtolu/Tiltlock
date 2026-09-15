"""Deterministic behavioral tilt signature detection engine."""

from typing import List, Optional
from tiltlock.config import get_config
from tiltlock.models import TradeFill, OrderCancel, TiltTriggerEvent


class TiltDetector:
    """Evaluates real-time trade telemetry against configurable behavioral tilt heuristics."""

    def __init__(self, baseline_size: float = 10.0):
        self.config = get_config().detection
        self.baseline_size = baseline_size
        self.fills: List[TradeFill] = []
        self.cancels: List[OrderCancel] = []
        self.loss_streak: int = 0
        self.cumulative_loss: float = 0.0
        self.last_stopout_time: Optional[int] = None
        self.last_loss_time: Optional[int] = None
        self.sl_tampered: bool = False

    def _refresh_loss_streak(self, fill: TradeFill) -> None:
        """Updates consecutive loss streak inside the configured evaluation window."""
        if fill.pnl < 0:
            if (
                self.last_loss_time is not None
                and (fill.timestamp_offset_sec - self.last_loss_time)
                > self.config.loss_streak_window_sec
            ):
                self.loss_streak = 1
            else:
                self.loss_streak += 1
            self.last_loss_time = fill.timestamp_offset_sec
            self.cumulative_loss += abs(fill.pnl)
        elif fill.pnl > 0:
            self.loss_streak = 0
            self.last_loss_time = None

    def ingest_fill(self, fill: TradeFill) -> TiltTriggerEvent:
        """Processes a new trade fill and checks for tilt triggers."""
        self.fills.append(fill)
        self._refresh_loss_streak(fill)

        # Check if this exit was a stop loss
        if fill.exit_reason == "STOP_LOSS":
            self.last_stopout_time = fill.timestamp_offset_sec

        # Check re-entry timing if this is an entry order (pnl == 0 or explicit entry)
        seconds_since_stop: Optional[int] = None
        if self.last_stopout_time is not None and fill.timestamp_offset_sec > self.last_stopout_time:
            seconds_since_stop = fill.timestamp_offset_sec - self.last_stopout_time

        size_ratio = fill.size / self.baseline_size if self.baseline_size > 0 else 1.0

        # Evaluate signatures
        signatures = []

        # 1. Rapid re-entry post stop-loss
        is_rapid_reentry = (
            seconds_since_stop is not None
            and seconds_since_stop <= self.config.reentry_after_stop_sec
            and fill.pnl == 0.0  # New entry
        )
        if is_rapid_reentry:
            signatures.append(f"RAPID_REENTRY ({seconds_since_stop}s post-stop)")

        # 2. Size escalation
        is_size_escalation = size_ratio >= self.config.size_escalation_ratio
        if is_size_escalation and (is_rapid_reentry or self.loss_streak > 0):
            signatures.append(f"SIZE_ESCALATION ({size_ratio:.1f}x baseline)")

        # 3. Loss streak
        if self.loss_streak >= self.config.loss_streak_n:
            signatures.append(f"LOSS_STREAK ({self.loss_streak} consecutive red trades)")

        # 4. Stop-loss tampering combined with drawdown
        if self.sl_tampered:
            signatures.append("STOP_LOSS_TAMPER (SL canceled while in drawdown)")

        # Determine if tilt trigger is met:
        # Either:
        # A) SL Tampered AND (Size Escalation OR Loss > 0)
        # B) Rapid Re-entry AND Size Escalation
        # C) Loss streak >= threshold
        is_triggered = False
        if self.sl_tampered and (is_size_escalation or fill.pnl < 0):
            is_triggered = True
        elif is_rapid_reentry and is_size_escalation:
            is_triggered = True
        elif self.loss_streak >= self.config.loss_streak_n:
            is_triggered = True

        summary = ", ".join(signatures) if signatures else "NORMAL_EXECUTION"

        return TiltTriggerEvent(
            is_triggered=is_triggered,
            signatures=signatures,
            loss_streak=self.loss_streak,
            size_ratio=size_ratio,
            seconds_since_last_stop=seconds_since_stop,
            sl_tampered=self.sl_tampered,
            session_loss=self.cumulative_loss,
            symbol=fill.symbol,
            summary=summary,
        )

    def ingest_cancel(self, cancel: OrderCancel) -> TiltTriggerEvent:
        """Processes an order cancellation event."""
        self.cancels.append(cancel)

        # If cancel happened while position is in floating drawdown
        if self.config.sl_tamper_while_drawdown and cancel.unrealized_pnl < 0:
            self.sl_tampered = True

        signatures = []
        if self.sl_tampered:
            signatures.append("STOP_LOSS_TAMPER (SL canceled while in drawdown)")

        return TiltTriggerEvent(
            is_triggered=self.sl_tampered,
            signatures=signatures,
            loss_streak=self.loss_streak,
            size_ratio=1.0,
            seconds_since_last_stop=None,
            sl_tampered=self.sl_tampered,
            session_loss=self.cumulative_loss,
            symbol=cancel.symbol,
            summary=", ".join(signatures) if signatures else "ORDER_CANCELED",
        )
