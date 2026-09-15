"""Real paper-mode execution runner wired to BgcCliBitgetClient."""

import json
import logging
import time
from typing import Any, Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tiltlock.config import AppConfig, get_config
from tiltlock.detector import TiltDetector
from tiltlock.diagnostician import TiltDiagnostician
from tiltlock.enforcer import BgcCliBitgetClient
from tiltlock.evolver import ChecklistEvolver
from tiltlock.models import TradeFill, OrderCancel, TiltTriggerEvent

logger = logging.getLogger("tiltlock.paper_runner")
console = Console()


def _merge_trigger(existing: TiltTriggerEvent | None, incoming: TiltTriggerEvent) -> TiltTriggerEvent:
    if existing is None:
        return incoming
    signatures = list(existing.signatures)
    for sig in incoming.signatures:
        if sig not in signatures:
            signatures.append(sig)
    return incoming.model_copy(
        update={
            "signatures": signatures,
            "summary": ", ".join(signatures) if signatures else incoming.summary,
            "session_loss": max(existing.session_loss, incoming.session_loss),
            "sl_tampered": existing.sl_tampered or incoming.sl_tampered,
            "size_ratio": max(existing.size_ratio, incoming.size_ratio),
            "loss_streak": max(existing.loss_streak, incoming.loss_streak),
        }
    )


def normalize_bgc_fill(item: Dict[str, Any], timestamp_offset_sec: int = 0) -> TradeFill:
    """Normalizes a raw bgc fill or order dictionary into a TradeFill model."""
    order_id = str(item.get("orderId") or item.get("fillId") or f"FILL-{timestamp_offset_sec}")
    symbol = str(item.get("symbol") or "TSLAUSDT_rToken")
    side = "BUY" if str(item.get("side", "")).upper() == "BUY" else "SELL"

    try:
        size = float(item.get("size") or item.get("baseVolume") or item.get("fillSize") or 10.0)
    except (ValueError, TypeError):
        size = 10.0

    try:
        entry_price = float(item.get("entryPrice") or item.get("price") or 0.0)
    except (ValueError, TypeError):
        entry_price = 0.0

    try:
        exit_price = float(item.get("exitPrice") or item.get("fillPrice") or item.get("price") or 0.0)
    except (ValueError, TypeError):
        exit_price = 0.0

    try:
        pnl = float(item.get("pnl") or item.get("realizedPnl") or item.get("profit") or 0.0)
    except (ValueError, TypeError):
        pnl = 0.0

    raw_reason = str(item.get("exitReason") or item.get("tradeType") or "")
    if "stop" in raw_reason.lower() or item.get("isStop"):
        exit_reason = "STOP_LOSS"
    elif "panic" in raw_reason.lower():
        exit_reason = "PANIC_MARKET_CLOSE"
    else:
        exit_reason = None

    narrative = item.get("narrative") or f"Paper trade fill on {symbol} (PnL: ${pnl:.2f})"

    return TradeFill(
        order_id=order_id,
        symbol=symbol,
        side=side,
        size=size,
        entry_price=entry_price,
        exit_price=exit_price,
        pnl=pnl,
        exit_reason=exit_reason,
        timestamp_offset_sec=timestamp_offset_sec,
        narrative=narrative,
    )


def normalize_bgc_cancel(item: Dict[str, Any], timestamp_offset_sec: int = 0) -> OrderCancel:
    """Normalizes a raw bgc cancel or modified order into an OrderCancel model."""
    order_id = str(item.get("orderId") or item.get("id") or f"CANCEL-{timestamp_offset_sec}")
    symbol = str(item.get("symbol") or "TSLAUSDT_rToken")
    side = "BUY" if str(item.get("side", "")).upper() == "BUY" else "SELL"
    try:
        price = float(item.get("price") or item.get("triggerPrice") or 0.0)
    except (ValueError, TypeError):
        price = 0.0
    try:
        unrealized_pnl = float(item.get("unrealizedPnl") or item.get("pnl") or 0.0)
    except (ValueError, TypeError):
        unrealized_pnl = 0.0
    narrative = item.get("narrative") or f"Stop-loss or limit order cancel on {symbol}"
    return OrderCancel(
        order_id=order_id,
        symbol=symbol,
        side=side,
        price=price,
        unrealized_pnl=unrealized_pnl,
        timestamp_offset_sec=timestamp_offset_sec,
        narrative=narrative,
    )


def run_paper(
    auto_yes: bool = False,
    aggressive: bool = False,
    use_fixture: bool = False,
    poll_override: Optional[int] = None,
) -> int:
    """Executes paper mode using real Bitget Agent Hub CLI ('bgc').

    1. Checks probe(): exits 1 if binary is missing or auth fails.
    2. If use_fixture=True: replays fixture sequence through BgcCliBitgetClient.
    3. Else: enters live polling loop via bgc order commands.
    """
    ok, code, msg = BgcCliBitgetClient.probe(paper_mode=True)
    if not ok:
        console.print()
        if code == "BINARY_NOT_FOUND":
            console.print(
                Panel.fit(
                    "[bold red][ERROR] Bitget Agent Hub CLI ('bgc') is not installed or not found on PATH.[/bold red]\n\n"
                    "[yellow]To install and authenticate 'bgc':[/yellow]\n"
                    "  1. Clone: git clone https://github.com/BitgetLimited/agent_hub\n"
                    "  2. Setup guide: https://www.bitget.careers/support/articles/12560603894122\n"
                    "  3. Add 'bgc' to your system PATH and authorize your Agentic sub-account:\n"
                    "     [cyan]bgc --paper-trading[/cyan]\n\n"
                    "[dim]For deterministic zero-network demo runs without bgc, use:[/dim]\n"
                    "  [bold green]python -m tiltlock.cli run --demo --yes[/bold green]",
                    title="[bold red]Dependency Missing[/bold red]",
                    border_style="red",
                )
            )
        else:
            console.print(
                Panel.fit(
                    f"[bold red][ERROR] Bitget Agent Hub CLI ('bgc') probe failed: {msg}[/bold red]\n\n"
                    "[yellow]Next Steps to Authorize Paper Trading Session:[/yellow]\n"
                    "  1. Open terminal and run: [cyan]bgc --paper-trading[/cyan]\n"
                    "  2. Complete the OAuth / Demo API Key authorization at:\n"
                    "     [cyan]https://www.bitget.careers/support/articles/12560603894122[/cyan]\n"
                    "  3. Verify probe success with: [cyan]bgc discover --paper-trading[/cyan]\n\n"
                    "[dim]For deterministic zero-network demo runs, use:[/dim]\n"
                    "  [bold green]python -m tiltlock.cli run --demo --yes[/bold green]",
                    title="[bold red]Paper Session Authentication Failed[/bold red]",
                    border_style="red",
                )
            )
        return 1

    cfg = get_config()
    evolver = ChecklistEvolver()
    checklist = evolver.load_checklist()
    client = BgcCliBitgetClient(paper_mode=True)
    detector = TiltDetector(baseline_size=10.0)
    diagnostician = TiltDiagnostician(mode="paper")

    # Clear previous lock
    client.clear_lock()

    console.print()
    console.print(
        Panel.fit(
            "[bold white on green] TILTLOCK: PAPER TRADING MODE [/bold white on green]\n"
            "[dim]Connected to Bitget Testnet via 'bgc' CLI[/dim]\n"
            f"[dim]Active Rules:[/dim] [cyan]{len(checklist.rules)}[/cyan] | "
            f"[dim]Execution Mode:[/dim] [bold yellow]{'Fixture Replay' if use_fixture else 'Live bgc Polling'}[/bold yellow] | "
            f"[dim]Aggressive Flatten:[/dim] [bold]{'Enabled' if (aggressive or cfg.policy.flatten_on_lock) else 'Disabled'}[/bold]",
            title="[bold green]Bitget Agentic Sub-Account (Paper)[/bold green]",
            border_style="green",
        )
    )

    if use_fixture:
        return _run_paper_fixture(client, detector, diagnostician, evolver, checklist, cfg, auto_yes, aggressive)
    else:
        return _run_paper_polling(client, detector, diagnostician, evolver, checklist, cfg, auto_yes, aggressive, poll_override)


def _run_paper_fixture(client, detector, diagnostician, evolver, checklist, cfg, auto_yes, aggressive) -> int:
    """Replays fixture telemetry into real BgcCliBitgetClient."""
    root = AppConfig.find_repo_root()
    fixture_path = root / "fixtures" / "tilt_sequence.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    console.print("[bold yellow]Ingesting Telemetry Stream into Paper Adapter...[/bold yellow]\n")
    triggered_event: TiltTriggerEvent | None = None
    for item in fixture["timeline"]:
        ev_type = item["event_type"]
        trigger = None
        if ev_type == "TRADE_FILL":
            fill = TradeFill(
                order_id=item["order_id"],
                symbol=item["symbol"],
                side=item["side"],
                size=item["size"],
                entry_price=item.get("entry_price"),
                exit_price=item.get("exit_price"),
                pnl=item.get("pnl", 0.0),
                exit_reason=item.get("exit_reason"),
                timestamp_offset_sec=item["timestamp_offset_sec"],
                narrative=item.get("narrative"),
            )
            trigger = detector.ingest_fill(fill)
        elif ev_type == "ORDER_CANCEL":
            cancel = OrderCancel(
                order_id=item["order_id"],
                symbol=item["symbol"],
                side=item["side"],
                price=item["price"],
                unrealized_pnl=item.get("unrealized_pnl", 0.0),
                timestamp_offset_sec=item["timestamp_offset_sec"],
                narrative=item.get("narrative"),
            )
            trigger = detector.ingest_cancel(cancel)

        if trigger is not None and trigger.is_triggered:
            triggered_event = _merge_trigger(triggered_event, trigger)

    if not triggered_event:
        console.print("[green]No tilt detected in fixture stream.[/green]")
        return 0

    return _apply_paper_lockout_and_evolution(
        client, diagnostician, evolver, checklist, triggered_event, fixture.get("market_regime"), cfg, auto_yes, aggressive
    )


def _run_paper_polling(client, detector, diagnostician, evolver, checklist, cfg, auto_yes, aggressive, poll_override=None) -> int:
    """Polls live fills from Bitget testnet via bgc."""
    poll_interval = cfg.paper.poll_interval_sec
    max_polls = poll_override or cfg.paper.max_polls
    seen_fills = set()
    seen_cancels = set()
    poll_count = 0

    console.print(f"[green]Polling bgc paper fills every {poll_interval}s (max: {max_polls} polls)...[/green]")
    console.print("[dim]Press Ctrl+C to terminate polling.[/dim]\n")

    try:
        while poll_count < max_polls:
            poll_count += 1
            # 1. Poll recent fills
            raw_fills = client.get_recent_fills()
            for item in raw_fills:
                fill_id = str(item.get("orderId") or item.get("fillId") or "")
                if fill_id and fill_id not in seen_fills:
                    seen_fills.add(fill_id)
                    fill = normalize_bgc_fill(item, timestamp_offset_sec=poll_count * poll_interval)
                    trigger = detector.ingest_fill(fill)
                    if trigger.is_triggered:
                        return _apply_paper_lockout_and_evolution(
                            client, diagnostician, evolver, checklist, trigger, None, cfg, auto_yes, aggressive
                        )

            # 2. Poll open orders / cancels
            raw_orders = client.get_open_orders()
            for item in raw_orders:
                status = str(item.get("status", "")).upper()
                if status in ("CANCELED", "CANCELLED"):
                    order_id = str(item.get("orderId") or item.get("id") or "")
                    if order_id and order_id not in seen_cancels:
                        seen_cancels.add(order_id)
                        cancel = normalize_bgc_cancel(item, timestamp_offset_sec=poll_count * poll_interval)
                        trigger = detector.ingest_cancel(cancel)
                        if trigger.is_triggered:
                            return _apply_paper_lockout_and_evolution(
                                client, diagnostician, evolver, checklist, trigger, None, cfg, auto_yes, aggressive
                            )

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Polling stopped by user.[/yellow]")
        return 0

    console.print("[dim]Polling window completed. No tilt signatures detected.[/dim]")
    return 0


def _apply_paper_lockout_and_evolution(
    client, diagnostician, evolver, checklist, triggered_event, market_regime, cfg, auto_yes, aggressive
) -> int:
    """Executes paper lockout, diagnosis, and checklist evolution.
    Strict 4-stage pipeline: Detect -> Diagnose -> Enforce -> Evolve
    """
    # 1. Diagnose (Stage order: Detect -> Diagnose -> Enforce -> Evolve)
    console.print("[bold cyan]Invoking Cognitive Diagnostics Engine (mode: paper)...[/bold cyan]")
    diagnosis = diagnostician.diagnose(
        trigger=triggered_event,
        checklist=checklist,
        market_context=market_regime,
    )

    # 2. Enforce (Real Agent Hub commands via bgc)
    console.print("[bold yellow]Executing Paper Enforcement via bgc CLI...[/bold yellow]")
    client.cancel_all_orders(triggered_event.symbol)
    client.cancel_strategy_orders(triggered_event.symbol)
    client.set_leverage(triggered_event.symbol, leverage=1)

    should_flatten = aggressive or cfg.policy.flatten_on_lock
    if should_flatten:
        client.close_position(triggered_event.symbol)

    clamped_minutes = max(
        cfg.cooldown.min_minutes,
        min(diagnosis.prescribed_cooldown_minutes, cfg.cooldown.max_minutes),
    )
    lock_state = client.set_cooldown(
        minutes=clamped_minutes,
        reason=triggered_event.summary,
        session_cost=triggered_event.session_loss,
    )

    flatten_line = "• [bold]position --action close:[/bold] Position flattened\n" if should_flatten else ""

    console.print(
        Panel(
            f"[bold white on red] ACCOUNT IN COOLDOWN — {clamped_minutes}:00 REMAINING [/bold white on red]\n\n"
            f"• [bold]order --action cancelAll:[/bold] Sent with --paper-trading\n"
            f"• [bold]strategy_order --action cancel:[/bold] Open strategy triggers purged\n"
            f"• [bold]position --action setLeverage:[/bold] 1x enforced on {triggered_event.symbol}\n"
            f"{flatten_line}"
            f"• [bold]Gateway Freeze:[/bold] Active until {lock_state.unlocks_at}",
            title="[bold red]Paper Enforcement Applied[/bold red]",
            border_style="red",
        )
    )

    # Test order gateway interception
    try:
        client.place_order(triggered_event.symbol, "BUY", 10.0, 240.0)
    except PermissionError as pe:
        console.print(f"[bold red][X] Gateway Intercepted Order:[/bold red] {pe}\n")

    # 3. Evolve
    accepted, updated_checklist = evolver.evaluate_rule_proposal(
        rule=diagnosis.evolved_rule,
        auto_accept_seconds=0 if auto_yes else cfg.policy.demo_auto_accept_seconds,
        auto_yes=auto_yes,
    )

    console.print(f"[bold green][OK] Paper mode completed. Checklist updated to v{updated_checklist.version}.[/bold green]")
    return 0
