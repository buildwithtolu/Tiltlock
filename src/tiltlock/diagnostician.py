"""Behavioral trade diagnostics engine with Qwen-3.8 integration and zero-network fallback."""

import json
import logging
import os
from typing import Dict, Any, Optional
import requests
from tiltlock.config import get_config
from tiltlock.models import TiltTriggerEvent, TiltDiagnosis, EvolvedRule, Checklist

logger = logging.getLogger("tiltlock.diagnostician")


CANNED_DEMO_DIAGNOSIS = TiltDiagnosis(
    pathology="SUNK_COST_ESCALATION",
    confidence=0.94,
    violated_checklist_rules=["R02"],
    sequence_audit=(
        "A clean -$150 rNVDA stop was followed 38 seconds later by an rTSLA entry at 25 contracts, "
        "breaking Rule R02's 15-contract cap (2.5x size). While the trade was already losing, the "
        "resting stop at $239.50 was canceled. The position was later panic-closed at -$400."
    ),
    cognitive_distortion="Loss aversion and sunk-cost thinking after the first red trade",
    session_cost=550.00,
    prescribed_cooldown_minutes=45,
    evolved_rule=EvolvedRule(
        rule_id="R03",
        condition="After any stop-loss exit on tech or US stock rTokens",
        hard_constraint="No re-entry on correlated tech contracts for 30 minutes",
        rationale="Stops immediate size-up and revenge trades right after a stop-out",
        created_at=None,
    ),
)


class TiltDiagnostician:
    """Diagnoses cognitive biases from telemetry and synthesizes evolved rules."""

    def __init__(self, mode: str = "demo"):
        self.mode = mode
        self.config = get_config()

    def diagnose(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> TiltDiagnosis:
        """Produces a structured behavioral tilt diagnosis and evolved rule."""
        # Override 2: --demo never calls network
        if self.mode == "demo":
            return CANNED_DEMO_DIAGNOSIS

        # Paper path: call Qwen only when a key is present; otherwise local fallback.
        try:
            return self._call_qwen_with_retry(trigger, checklist, market_context)
        except Exception as e:
            logger.warning("Qwen diagnostics unavailable (%s). Using local fallback.", e)
            return self._create_fallback_diagnosis(trigger, checklist)

    def _call_qwen_with_retry(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]],
    ) -> TiltDiagnosis:
        """Calls Qwen API with a single retry and Pydantic validation."""
        api_key = os.getenv("BITGET_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        if not api_key:
            raise RuntimeError(
                "No Qwen API key set (BITGET_QWEN_API_KEY / QWEN_API_KEY). "
                "Skipping remote review."
            )

        payload = self._build_prompt_payload(trigger, checklist, market_context)
        url = self.config.policy.qwen_api_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

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
                                    "intraday traders. Analyze the execution sequence where "
                                    "behavioral tilt triggered an automated cooldown. Ground your "
                                    "diagnosis strictly in order telemetry, timing, and active "
                                    "checklist rules. Output strictly valid JSON matching the "
                                    "exact schema. Keep sequence_audit to 120 words or fewer."
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

                # Clamp cooldown minutes locally
                cd = parsed.get("prescribed_cooldown_minutes", self.config.cooldown.default_minutes)
                parsed["prescribed_cooldown_minutes"] = max(
                    self.config.cooldown.min_minutes,
                    min(cd, self.config.cooldown.max_minutes),
                )

                diagnosis = TiltDiagnosis(**parsed)
                return diagnosis
            except Exception as ex:
                if attempt == 1:
                    raise ex

        raise RuntimeError("Qwen diagnostic retry exhausted")

    def _create_fallback_diagnosis(
        self, trigger: TiltTriggerEvent, checklist: Checklist
    ) -> TiltDiagnosis:
        """Deterministic template fallback with confidence: 0.0 to prevent crashes."""
        pathology = "REVENGE_TRADING"
        if trigger.sl_tampered:
            pathology = "STOP_LOSS_TAMPERING"
        elif trigger.size_ratio >= 2.0:
            pathology = "SUNK_COST_ESCALATION"

        violated = []
        for r in checklist.rules:
            if "sizing" in r.hard_constraint.lower() and trigger.size_ratio >= 1.5:
                violated.append(r.rule_id)

        next_rule_num = len(checklist.rules) + 1
        rule_id = f"R{next_rule_num:02d}"

        return TiltDiagnosis(
            pathology=pathology,
            confidence=0.0,
            violated_checklist_rules=violated or ["R02"],
            sequence_audit=(
                f"Model review unavailable, so a local review was used. "
                f"Signals: {trigger.summary}. Session loss ${trigger.session_loss:.2f} on "
                f"{trigger.symbol} with {trigger.size_ratio:.1f}x size vs baseline."
            ),
            cognitive_distortion="Loss aversion with escalating risk after losses",
            session_cost=trigger.session_loss,
            prescribed_cooldown_minutes=self.config.cooldown.default_minutes,
            evolved_rule=EvolvedRule(
                rule_id=rule_id,
                condition=f"After a realized loss on {trigger.symbol}",
                hard_constraint="Wait 30 minutes before opening a new position",
                rationale="Gives time to reset after a tilt sequence",
            ),
        )

    def _build_prompt_payload(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "trigger_signatures": trigger.signatures,
            "loss_streak": trigger.loss_streak,
            "size_ratio": trigger.size_ratio,
            "session_loss": trigger.session_loss,
            "symbol": trigger.symbol,
            "market_context": market_context or {"status": "High Intraday Volatility"},
            "active_rules": [r.model_dump() for r in checklist.rules],
        }
