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
        "Trader took a legitimate -$150 stop on NVDA, then within 38 seconds impulsively entered "
        "TSLA at 25 contracts—violating Rule R02's 15-contract ceiling (2.5x size escalation). "
        "As the market moved against the oversized position, the trader manually canceled the resting "
        "stop-loss at $239.50, turning a disciplined risk-managed trade into an undisciplined "
        "-$400 panic liquidation."
    ),
    cognitive_distortion="Loss Aversion & Sunk Cost Fallacy (refusal to accept initial red trade)",
    session_cost=550.00,
    prescribed_cooldown_minutes=45,
    evolved_rule=EvolvedRule(
        rule_id="R03",
        condition="Following any realized stop-loss exit on tech/US stock rTokens",
        hard_constraint="Mandatory 30-minute re-entry lockout on all correlated tech equity contracts",
        rationale="Prevents immediate impulsive size-escalation and revenge trading post stop-out",
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

        # Live / Paper path with Qwen call and fail-safe fallback
        try:
            return self._call_qwen_with_retry(trigger, checklist, market_context)
        except Exception as e:
            logger.warning(f"Qwen diagnostics failed ({e}). Using deterministic fallback.")
            return self._create_fallback_diagnosis(trigger, checklist)

    def _call_qwen_with_retry(
        self,
        trigger: TiltTriggerEvent,
        checklist: Checklist,
        market_context: Optional[Dict[str, Any]],
    ) -> TiltDiagnosis:
        """Calls Qwen API with a single retry and Pydantic validation."""
        payload = self._build_prompt_payload(trigger, checklist, market_context)
        url = self.config.policy.qwen_api_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = os.getenv("BITGET_QWEN_API_KEY") or os.getenv("QWEN_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

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
                f"Automated fallback diagnosis: Triggered on {trigger.summary}. "
                f"Trader incurred ${trigger.session_loss:.2f} in session losses with a {trigger.size_ratio:.1f}x "
                f"position size escalation on {trigger.symbol}. Stop discipline violated."
            ),
            cognitive_distortion="Loss Aversion & Tilting Escalation",
            session_cost=trigger.session_loss,
            prescribed_cooldown_minutes=self.config.cooldown.default_minutes,
            evolved_rule=EvolvedRule(
                rule_id=rule_id,
                condition=f"After any realized loss on {trigger.symbol}",
                hard_constraint="Mandatory 30-minute cooling period before re-entry",
                rationale="Automated containment rule generated from tilt event",
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
