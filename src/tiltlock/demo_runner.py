"""Deterministic offline demo runner."""

import json
import time
from rich.console import Console
from rich.panel import Panel
from tiltlock.config import AppConfig, get_config
from tiltlock.detector import TiltDetector
from tiltlock.diagnostician import TiltDiagnostician
from tiltlock.display import print_checklist, print_diagnosis
from tiltlock.enforcer import MockBitgetClient
from tiltlock.evolver import ChecklistEvolver
from tiltlock.models import TradeFill, OrderCancel, TiltTriggerEvent

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


def run_demo(auto_yes: bool = False, speed_multiplier: float = 1.0, aggressive: bool = False) -> int:
    """Run the offline demo: Detect → Diagnose → Enforce → Evolve."""
    root = AppConfig.find_repo_root()
    fixture_path = root / "fixtures" / "tilt_sequence.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture = json.load(f)

    cfg = get_config()
    evolver = ChecklistEvolver()
    checklist = evolver.reset_to_baseline()
    detector = TiltDetector(baseline_size=10.0)
    enforcer = MockBitgetClient()
    diagnostician = TiltDiagnostician(mode="demo")
    symbol = fixture["market_regime"]["symbol"]

    enforcer.clear_lock()

    console.print()
    console.print(
        Panel.fit(
            "[bold]TiltLock offline demo[/bold]\n"
            f"Account: [bold]{fixture['trader_account']['account_id']}[/bold] "
            f"(${fixture['trader_account']['starting_balance_usdt']:,.2f} USDT) | "
            f"Rules: [cyan]{len(checklist.rules)}[/cyan] | "
            "Mode: [yellow]demo (no network)[/yellow]",
            title="Session",
            border_style="blue",
        )
    )

    print_checklist(checklist, "Starting checklist")
    console.print()

    delay = 0.8 / speed_multiplier if not auto_yes else 0.2
    console.print("[bold]Replaying demo trades...[/bold]\n")

    triggered_event: TiltTriggerEvent | None = None
    for item in fixture["timeline"]:
        time.sleep(delay)
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
            pnl_str = (
                f"[red]${fill.pnl:,.2f}[/red]"
                if fill.pnl < 0
                else f"[green]+${fill.pnl:,.2f}[/green]"
                if fill.pnl > 0
                else "[dim]$0.00[/dim]"
            )
            console.print(
                f"[cyan][T+{item['timestamp_offset_sec']:03d}s][/cyan] "
                f"[bold]{fill.side} {fill.size} {fill.symbol}[/bold] | "
                f"PnL: {pnl_str} | [dim]{fill.narrative}[/dim]"
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
                f"[bold]{cancel.order_id} ({cancel.symbol})[/bold] @ ${cancel.price:.2f} | "
                f"Unrealized: [red]${cancel.unrealized_pnl:.2f}[/red] | "
                f"[dim]{cancel.narrative}[/dim]"
            )

        if trigger is not None and trigger.is_triggered:
            triggered_event = _merge_trigger(triggered_event, trigger)

    console.print()
    if not triggered_event:
        console.print("[green]No tilt patterns found in this session.[/green]")
        return 0

    console.print(
        Panel.fit(
            f"[bold red]Tilt pattern detected[/bold red]\n"
            f"Signals: {', '.join(triggered_event.signatures)}\n"
            f"Session loss: [red]${triggered_event.session_loss:,.2f}[/red] | "
            f"Size vs baseline: [red]{triggered_event.size_ratio:.1f}x[/red]",
            title="Detect",
            border_style="red",
        )
    )
    time.sleep(delay)

    console.print("[bold]Reviewing the trade sequence...[/bold]")
    diagnosis = diagnostician.diagnose(
        trigger=triggered_event,
        checklist=checklist,
        market_context=fixture.get("market_regime"),
    )
    print_diagnosis(diagnosis)
    console.print()
    time.sleep(delay)

    cooldown_minutes = max(
        cfg.cooldown.min_minutes,
        min(diagnosis.prescribed_cooldown_minutes, cfg.cooldown.max_minutes),
    )
    should_flatten = aggressive or cfg.policy.flatten_on_lock
    console.print(
        "[bold]Applying account protections[/bold] "
        "[dim](demo simulation of Bitget Agent Hub actions)[/dim]"
    )
    canceled_orders = enforcer.cancel_all_orders(symbol)
    canceled_strategies = enforcer.cancel_strategy_orders(symbol)
    enforcer.set_leverage(symbol, leverage=1)

    closed_line = ""
    if should_flatten:
        enforcer.close_position(symbol)
        closed_line = f"\n• Closed open position on [cyan]{symbol}[/cyan]"

    lock_state = enforcer.set_cooldown(
        minutes=cooldown_minutes,
        reason=triggered_event.summary,
        session_cost=triggered_event.session_loss,
    )

    console.print(
        Panel(
            f"[bold white on red] COOLDOWN {cooldown_minutes} MIN [/bold white on red]\n\n"
            f"• Canceled [cyan]{len(canceled_orders)}[/cyan] open order(s)\n"
            f"• Canceled [cyan]{len(canceled_strategies)}[/cyan] stop/trigger order(s)\n"
            f"• Set leverage to [cyan]1x[/cyan] on {symbol}"
            f"{closed_line}\n"
            f"• Local order gateway locked until [yellow]{lock_state.unlocks_at}[/yellow]",
            title="Enforce",
            border_style="red",
        )
    )

    console.print("[dim]Testing a new order while locked...[/dim]")
    try:
        enforcer.place_order(symbol, "BUY", 10.0, 240.0)
        console.print("[bold red]Unexpected: order was accepted during cooldown.[/bold red]")
    except PermissionError as pe:
        console.print(f"[bold red]Blocked:[/bold red] {pe}\n")

    time.sleep(delay)

    auto_sec = 0 if auto_yes else cfg.policy.demo_auto_accept_seconds
    accepted, updated_checklist = evolver.evaluate_rule_proposal(
        rule=diagnosis.evolved_rule,
        auto_accept_seconds=auto_sec,
        auto_yes=auto_yes,
    )

    console.print()
    print_checklist(updated_checklist, f"Updated checklist (v{updated_checklist.version})")
    if accepted:
        console.print(
            f"[bold green][OK] Added {diagnosis.evolved_rule.rule_id} to your checklist.[/bold green]"
        )
    console.print("[bold green][OK] Demo finished.[/bold green]\n")
    return 0
