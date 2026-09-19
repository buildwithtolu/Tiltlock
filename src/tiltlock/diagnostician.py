"""Trade review engine: trigger-based local review, optional Qwen, optional signal context."""

import json
import logging
import os
from typing import Any, Dict, Optional
import requests
from tiltlock.config import get_config
from tiltlock.models import TiltTriggerEvent, TiltDiagnosis, EvolvedRule, Checklist

logger = logging.getLogger("tiltlock.diagnostician")


class TiltDiagnostician:
    """Builds a session review from detector output. Optional live LLM."""

    def __init__(self, mode: str = "demo", live_llm: bool = False):
        self.mode = mode
        self.live_llm = live_llm
        self.config = get_config()

    def diagnose(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> TiltDiagnosis:
        local = self.build_from_trigger(trigger, checklist, market_context)
        if not self.live_llm:
            return local
        try:
            return self._call_qwen_with_retry(trigger, checklist, market_context)
        except Exception as e:
            logger.warning("Qwen diagnostics unavailable (%s). Using local review.", e)
            return local

    def build_from_trigger(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> TiltDiagnosis:
        """Deterministic review that changes when the session numbers change."""
        sig_text = " ".join(trigger.signatures).upper()
        if trigger.sl_tampered or "STOP_LOSS_TAMPER" in sig_text:
            pathology = "STOP_LOSS_TAMPERING"
            distortion = "Loss aversion: cutting the stop instead of cutting the trade"
            confidence = 0.86
        elif trigger.size_ratio >= 2.0 or "SIZE_ESCALATION" in sig_text:
            pathology = "SUNK_COST_ESCALATION"
            distortion = "Sunk-cost thinking: sizing up to win back the last red trade"
            confidence = 0.84
        else:
            pathology = "REVENGE_TRADING"
            distortion = "Revenge trading: re-entering too fast after a loss"
            confidence = 0.80
        if trigger.sl_tampered and trigger.size_ratio >= 2.0:
            pathology = "SUNK_COST_ESCALATION"
            distortion = (
                "Loss aversion and sunk-cost thinking after the first red trade"
            )
            confidence = 0.90

        violated = []
        for rule in checklist.rules:
            constraint = rule.hard_constraint.lower()
            if "sizing" in constraint and trigger.size_ratio >= 1.5:
                violated.append(rule.rule_id)
            if "5 minute" in constraint or "within 5" in constraint:
                continue

        reentry = trigger.seconds_since_last_stop
        reentry_bit = (
            f" Re-entry was {reentry}s after the stop."
            if reentry is not None
            else ""
        )
        signal_bit = ""
        if isinstance(market_context, dict):
            summary = market_context.get("summary") or market_context.get("signal_summary")
            if summary:
                signal_bit = f" Market context ({market_context.get('source', 'signal')}): {summary}."

        audit = (
            f"{trigger.symbol} session loss ${trigger.session_loss:,.2f} at "
            f"{trigger.size_ratio:.1f}x baseline size. Signals: {trigger.summary or ', '.join(trigger.signatures)}."
            f"{reentry_bit}{signal_bit}"
        )
        words = audit.split()
        if len(words) > 120:
            audit = " ".join(words[:120])

        next_num = len(checklist.rules) + 1
        rule_id = f"R{next_num:02d}"
        symbol = trigger.symbol or "this market"

        return TiltDiagnosis(
            pathology=pathology,
            confidence=confidence,
            violated_checklist_rules=violated or (["R02"] if trigger.size_ratio >= 1.5 else []),
            sequence_audit=audit,
            cognitive_distortion=distortion,
            session_cost=trigger.session_loss,
            prescribed_cooldown_minutes=self.config.cooldown.default_minutes,
            evolved_rule=EvolvedRule(
                rule_id=rule_id,
                condition=f"After a stop-loss or realized loss on {symbol}",
                hard_constraint="No re-entry on correlated contracts for 30 minutes",
                rationale="Stops immediate size-up and revenge trades right after a stop-out",
            ),
        )

    def _call_qwen_with_retry(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]],
    ) -> TiltDiagnosis:
        api_key = os.getenv("BITGET_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No Qwen API key set (BITGET_QWEN_API_KEY / QWEN_API_KEY)."
            )

        payload = {
            "trigger_signatures": trigger.signatures,
            "loss_streak": trigger.loss_streak,
            "size_ratio": trigger.size_ratio,
            "session_loss": trigger.session_loss,
            "symbol": trigger.symbol,
            "market_context": market_context or {},
            "active_rules": [r.model_dump() for r in checklist.rules],
        }
        url = self.config.policy.qwen_api_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json={
                        "model": self.config.policy.qwen_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are the behavioral trade auditor for Bitget discretionary "
                                    "intraday traders. Ground the diagnosis in order telemetry and "
                                    "checklist rules. Output strictly valid JSON. Keep "
                                    "sequence_audit to 120 words or fewer."
                                ),
                            },
                            {"role": "user", "content": json.dumps(payload)},
                        ],
                        "temperature": 0.1 if attempt > 0 else 0.2,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=8.0,
                )
                resp.raise_for_status()
                raw_json = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(raw_json)
                cd = parsed.get(
                    "prescribed_cooldown_minutes", self.config.cooldown.default_minutes
                )
                parsed["prescribed_cooldown_minutes"] = max(
                    self.config.cooldown.min_minutes,
                    min(cd, self.config.cooldown.max_minutes),
                )
                return TiltDiagnosis(**parsed)
            except Exception as ex:
                last_error = ex
        raise RuntimeError(f"Qwen diagnostic retry exhausted: {last_error}")
