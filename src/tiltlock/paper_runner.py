"""Paper-mode runner using Bitget Demo Trading through bgc."""

import json
import logging
import time
from typing import Any, Dict, Optional
from rich.console import Console
from rich.panel import Panel

from tiltlock.config import AppConfig, get_config
from tiltlock.detector import TiltDetector
from tiltlock.diagnostician import TiltDiagnostician
from tiltlock.display import print_diagnosis
from tiltlock.enforcer import BgcCliBitgetClient
from tiltlock.evolver import ChecklistEvolver
from tiltlock.review_store import save_review
from tiltlock.signals import fetch_sentiment_snapshot
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
    """Normalize a bgc fill payload into TradeFill."""
    order_id = str(item.get("orderId") or item.get("fillId") or f"FILL-{timestamp_offset_sec}")
    symbol = str(item.get("symbol") or "UNKNOWN")
    side = "BUY" if str(item.get("side", "")).upper() == "BUY" else "SELL"

    try:
        size = float(item.get("size") or item.get("baseVolume") or item.get("fillSize") or 0.0)
    except (ValueError, TypeError):
        size = 0.0

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

    narrative = item.get("narrative") or f"Fill on {symbol} (PnL ${pnl:.2f})"

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
    """Normalize a bgc cancel payload into OrderCancel."""
    order_id = str(item.get("orderId") or item.get("id") or f"CANCEL-{timestamp_offset_sec}")
    symbol = str(item.get("symbol") or "UNKNOWN")
    side = "BUY" if str(item.get("side", "")).upper() == "BUY" else "SELL"
    try:
        price = float(item.get("price") or item.get("triggerPrice") or 0.0)
    except (ValueError, TypeError):
        price = 0.0
    try:
        unrealized_pnl = float(item.get("unrealizedPnl") or item.get("pnl") or 0.0)
    except (ValueError, TypeError):
        unrealized_pnl = 0.0
    narrative = item.get("narrative") or f"Canceled order on {symbol}"
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
    allow_writes: bool = False,
    live_llm: bool = False,
    use_signal: bool = True,
) -> int:
    """Run paper mode through real bgc Demo Trading commands."""
    ok, code, msg = BgcCliBitgetClient.probe(paper_mode=True)
    if not ok:
        console.print()
        if code == "BINARY_NOT_FOUND":
            console.print(
                Panel.fit(
                    "[bold red]bgc is not installed[/bold red]\n\n"
                    "Install:\n"
                    "  [cyan]npm install -g @bitget-ai/bitget-agent-cli[/cyan]\n"
                    "Then reopen your terminal and run [cyan]bgc --version[/cyan]\n\n"
                    "No Bitget account? Use the offline demo:\n"
                    "  [green]python -m tiltlock.cli run --demo --yes[/green]",
                    title="Setup needed",
                    border_style="red",
                )
            )
        else:
            console.print(
                Panel.fit(
                    f"[bold red]Could not start Bitget Demo Trading session[/bold red]\n\n"
                    f"{msg}\n\n"
                    "1. Set BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE\n"
                    "2. Use a Demo API key with Spot + Futures order/holdings\n"
                    "3. Check with: [cyan]bgc discover --paper-trading[/cyan]\n\n"
                    "Offline demo:\n"
                    "  [green]python -m tiltlock.cli run --demo --yes[/green]",
                    title="Auth needed",
                    border_style="red",
                )
            )
        return 1

    cfg = get_config()
    evolver = ChecklistEvolver()
    checklist = evolver.load_checklist()
    # --yes already means non-interactive consent for Demo Trading writes.
    allow_writes = allow_writes or auto_yes

    if not allow_writes:
        console.print(
            Panel.fit(
                "[bold yellow]Paper mode can cancel orders and change leverage on your Demo account.[/bold yellow]\n\n"
                "Re-run with [cyan]--yes[/cyan] or [cyan]--i-understand[/cyan] to allow those write actions.\n"
                "Offline demo needs no consent: [green]python -m tiltlock.cli run --demo --yes[/green]",
                title="Write consent required",
                border_style="yellow",
            )
        )
        return 1

    client = BgcCliBitgetClient(paper_mode=True, allow_writes=True)
    detector = TiltDetector(baseline_size=10.0)
    diagnostician = TiltDiagnostician(mode="paper", live_llm=live_llm)
    client.clear_lock()

    console.print()
    console.print(
        Panel.fit(
            "[bold]TiltLock paper mode[/bold]\n"
            "Connected through [cyan]bgc --paper-trading[/cyan]\n"
            f"Rules: [cyan]{len(checklist.rules)}[/cyan] | "
            f"Path: [yellow]{'fixture replay' if use_fixture else 'live polling'}[/yellow] | "
            f"Flatten: [bold]{'on' if (aggressive or cfg.policy.flatten_on_lock) else 'off'}[/bold]\n"
            "[dim]Cooldown lock is local to TiltLock. Other bots/terminals are not blocked.[/dim]",
            title="Bitget Demo Trading",
            border_style="green",
        )
    )

    if use_fixture:
        return _run_paper_fixture(
            client,
            detector,
            diagnostician,
            evolver,
            checklist,
            cfg,
            auto_yes,
            aggressive,
            use_signal,
        )
    return _run_paper_polling(
        client,
        detector,
        diagnostician,
        evolver,
        checklist,
        cfg,
        auto_yes,
        aggressive,
        poll_override,
        use_signal,
    )


def _run_paper_fixture(
    client, detector, diagnostician, evolver, checklist, cfg, auto_yes, aggressive, use_signal=True
) -> int:
    root = AppConfig.find_repo_root()
    fixture_path = root / "fixtures" / "tilt_sequence.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    console.print("[bold]Replaying demo trades through bgc...[/bold]\n")
    triggered_event: TiltTriggerEvent | None = None
    for item in fixture["timeline"]:
        trigger = None
        if item["event_type"] == "TRADE_FILL":
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
            console.print(
                f"[cyan][T+{item['timestamp_offset_sec']:03d}s][/cyan] "
                f"{fill.side} {fill.size} {fill.symbol} | PnL ${fill.pnl:,.2f}"
            )
        elif item["event_type"] == "ORDER_CANCEL":
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
            console.print(
                f"[red][T+{item['timestamp_offset_sec']:03d}s] CANCEL[/red] "
                f"{cancel.order_id} @ ${cancel.price:.2f}"
            )

        if trigger is not None and trigger.is_triggered:
            triggered_event = _merge_trigger(triggered_event, trigger)

    if not triggered_event:
        console.print("[green]No tilt patterns in the fixture.[/green]")
        return 0

    return _apply_paper_lockout_and_evolution(
        client,
        diagnostician,
        evolver,
        checklist,
        triggered_event,
        fixture.get("market_regime"),
        cfg,
        auto_yes,
        aggressive,
        use_signal,
    )


def _run_paper_polling(
    client,
    detector,
    diagnostician,
    evolver,
    checklist,
    cfg,
    auto_yes,
    aggressive,
    poll_override=None,
    use_signal=True,
) -> int:
    poll_interval = cfg.paper.poll_interval_sec
    max_polls = poll_override or cfg.paper.max_polls
    seen_fills = set()
    seen_cancels = set()
    poll_count = 0

    console.print(
        f"[green]Watching Demo Trading fills every {poll_interval}s "
        f"(max {max_polls} checks). Ctrl+C to stop.[/green]\n"
    )

    try:
        while poll_count < max_polls:
            poll_count += 1
            for item in client.get_recent_fills():
                fill_id = str(item.get("orderId") or item.get("fillId") or "")
                if fill_id and fill_id not in seen_fills:
                    seen_fills.add(fill_id)
                    fill = normalize_bgc_fill(item, timestamp_offset_sec=poll_count * poll_interval)
                    trigger = detector.ingest_fill(fill)
                    if trigger.is_triggered:
                        return _apply_paper_lockout_and_evolution(
                            client,
                            diagnostician,
                            evolver,
                            checklist,
                            trigger,
                            None,
                            cfg,
                            auto_yes,
                            aggressive,
                            use_signal,
                        )

            for item in client.get_open_orders():
                status = str(item.get("status", "")).upper()
                if status in ("CANCELED", "CANCELLED"):
                    order_id = str(item.get("orderId") or item.get("id") or "")
                    if order_id and order_id not in seen_cancels:
                        seen_cancels.add(order_id)
                        cancel = normalize_bgc_cancel(
                            item, timestamp_offset_sec=poll_count * poll_interval
                        )
                        trigger = detector.ingest_cancel(cancel)
                        if trigger.is_triggered:
                            return _apply_paper_lockout_and_evolution(
                                client,
                                diagnostician,
                                evolver,
                                checklist,
                                trigger,
                                None,
                                cfg,
                                auto_yes,
                                aggressive,
                                use_signal,
                            )

            time.sleep(poll_interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching fills.[/yellow]")
        return 0

    console.print(
        "[yellow]Watch window finished with no tilt patterns.[/yellow]\n"
        f"[dim]Checked {max_polls} times every {poll_interval}s. "
        "Place Demo trades that match tilt rules, or use --paper --fixture --yes.[/dim]"
    )
    return 0


def _apply_paper_lockout_and_evolution(
    client,
    diagnostician,
    evolver,
    checklist,
    triggered_event,
    market_regime,
    cfg,
    auto_yes,
    aggressive,
    use_signal=True,
) -> int:
    console.print(
        Panel.fit(
            f"[bold red]Tilt pattern detected[/bold red]\n{triggered_event.summary}\n"
            f"Session loss: ${triggered_event.session_loss:,.2f}",
            title="Detect",
            border_style="red",
        )
    )

    console.print("[bold]Reviewing the trade sequence...[/bold]")
    market_context = dict(market_regime or {})
    if use_signal:
        snapshot = fetch_sentiment_snapshot()
        market_context["source"] = snapshot.get("source")
        market_context["summary"] = snapshot.get("summary")
        market_context["signal_status"] = snapshot.get("status")
    diagnosis = diagnostician.diagnose(
        trigger=triggered_event,
        checklist=checklist,
        market_context=market_context,
    )
    save_review(diagnosis, extra={"mode": "paper", "signal": market_context.get("summary")})
    print_diagnosis(diagnosis)

    console.print("[bold]Sending protections through bgc...[/bold]")
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

    flatten_line = "• Closed open position\n" if should_flatten else ""
    console.print(
        Panel(
            f"[bold white on red] COOLDOWN {clamped_minutes} MIN [/bold white on red]\n\n"
            f"• cancelAll sent via bgc --paper-trading\n"
            f"• strategy/stop orders canceled\n"
            f"• leverage set to 1x on {triggered_event.symbol}\n"
            f"{flatten_line}"
            f"• local gateway locked until {lock_state.unlocks_at}",
            title="Enforce",
            border_style="red",
        )
    )

    try:
        client.place_order(triggered_event.symbol, "BUY", 10.0, 240.0)
        console.print("[bold red]Unexpected: order accepted during cooldown.[/bold red]")
    except PermissionError as pe:
        console.print(f"[bold red]Blocked:[/bold red] {pe}\n")

    accepted, updated_checklist = evolver.evaluate_rule_proposal(
        rule=diagnosis.evolved_rule,
        auto_accept_seconds=0 if auto_yes else cfg.policy.demo_auto_accept_seconds,
        auto_yes=auto_yes,
    )

    if accepted:
        console.print(
            f"[bold green][OK] Checklist updated to v{updated_checklist.version}.[/bold green]"
        )
    else:
        console.print(
            f"[yellow]Rule not added. Checklist remains v{updated_checklist.version}.[/yellow]"
        )
    return 0
