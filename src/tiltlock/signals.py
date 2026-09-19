"""Fail-open Bitget Signal (public MCP) client. One skill: sentiment-analyst."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger("tiltlock.signals")

BITGET_SIGNAL_MCP_URL = "https://datahub.noxiaohao.com/mcp"
SIGNAL_TIMEOUT_SEC = 4.0


def _parse_sse_json(text: str) -> Dict[str, Any]:
    for line in text.splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                return json.loads(payload)
    return json.loads(text)


def _fear_greed_label(value: float) -> str:
    if value <= 25:
        return "Extreme Fear"
    if value <= 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def _extract_index(result: Dict[str, Any]) -> Optional[float]:
    """Pull a numeric Fear & Greed value from MCP tool result shapes."""
    if not isinstance(result, dict):
        return None
    inner = result.get("result", result)
    content = inner.get("content") if isinstance(inner, dict) else None
    blob: Any = inner
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            try:
                blob = json.loads(first["text"])
            except (TypeError, json.JSONDecodeError):
                blob = first.get("text")
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            return None
    if not isinstance(blob, dict):
        return None
    for key in ("value", "data", "index", "fear_greed", "fgi"):
        val = blob.get(key)
        if isinstance(val, dict):
            for nested in ("value", "index", "score"):
                if nested in val:
                    try:
                        return float(val[nested])
                    except (TypeError, ValueError):
                        continue
        try:
            if val is not None and not isinstance(val, (dict, list)):
                return float(val)
        except (TypeError, ValueError):
            continue
    return None


def fetch_sentiment_snapshot(timeout_sec: float = SIGNAL_TIMEOUT_SEC) -> Dict[str, Any]:
    """Call bitget-signal MCP tool sentiment_index(action=current).

    Never raises. On timeout/error returns status=unavailable so the core loop continues.
    """
    unavailable = {
        "status": "unavailable",
        "source": "bitget-signal:sentiment-analyst",
        "summary": "bitget-signal unavailable",
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    session = requests.Session()
    try:
        init = session.post(
            BITGET_SIGNAL_MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "tiltlock", "version": "0.1.0"},
                },
            },
            headers=headers,
            timeout=timeout_sec,
        )
        init.raise_for_status()
        sid = init.headers.get("mcp-session-id")
        if sid:
            headers["mcp-session-id"] = sid
        session.post(
            BITGET_SIGNAL_MCP_URL,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=headers,
            timeout=timeout_sec,
        )
        call = session.post(
            BITGET_SIGNAL_MCP_URL,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "sentiment_index",
                    "arguments": {"action": "current"},
                },
            },
            headers=headers,
            timeout=timeout_sec,
        )
        call.raise_for_status()
        parsed = _parse_sse_json(call.text)
        value = _extract_index(parsed)
        if value is None:
            logger.info("bitget-signal returned no numeric index")
            return {
                "status": "unavailable",
                "source": "bitget-signal:sentiment-analyst",
                "summary": "bitget-signal returned no Fear & Greed value",
            }
        label = _fear_greed_label(value)
        return {
            "status": "ok",
            "source": "bitget-signal:sentiment-analyst",
            "fear_greed": value,
            "label": label,
            "summary": f"Fear & Greed {value:.0f} ({label})",
        }
    except Exception as exc:
        logger.info("bitget-signal skipped: %s", exc)
        return unavailable
