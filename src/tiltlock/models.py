"""Pydantic models and schemas for TiltLock."""

from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class TradeFill(BaseModel):
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    size: float
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    exit_reason: Optional[str] = None  # e.g., "STOP_LOSS", "TAKE_PROFIT", "PANIC_MARKET_CLOSE"
    timestamp_offset_sec: int = 0
    narrative: Optional[str] = None


class OrderCancel(BaseModel):
    order_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    price: float
    unrealized_pnl: float = 0.0
    timestamp_offset_sec: int = 0
    narrative: Optional[str] = None


class TiltTriggerEvent(BaseModel):
    is_triggered: bool
    signatures: List[str] = Field(default_factory=list)
    loss_streak: int = 0
    size_ratio: float = 1.0
    seconds_since_last_stop: Optional[int] = None
    sl_tampered: bool = False
    session_loss: float = 0.0
    symbol: str = "UNKNOWN"
    summary: str = ""


class EvolvedRule(BaseModel):
    rule_id: str
    condition: str
    hard_constraint: str
    rationale: str
    created_at: Optional[str] = None


class Checklist(BaseModel):
    version: int = 1
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    rules: List[EvolvedRule] = Field(default_factory=list)


class TiltDiagnosis(BaseModel):
    pathology: str  # e.g., "SUNK_COST_ESCALATION", "REVENGE_TRADING", "STOP_LOSS_TAMPERING"
    confidence: float = 1.0
    violated_checklist_rules: List[str] = Field(default_factory=list)
    sequence_audit: str  # Capped at <= 120 words
    cognitive_distortion: str
    session_cost: float
    prescribed_cooldown_minutes: int
    evolved_rule: EvolvedRule


class LockState(BaseModel):
    is_locked: bool = False
    locked_at: Optional[str] = None
    unlocks_at: Optional[str] = None
    reason: Optional[str] = None
    cooldown_minutes: int = 0
    session_cost: float = 0.0
