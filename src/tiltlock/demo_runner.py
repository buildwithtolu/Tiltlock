"""Deterministic demo runner driving the judge demonstration."""

import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from tiltlock.config import AppConfig, get_config
from tiltlock.detector import TiltDetector
from tiltlock.diagnostician import TiltDiagnostician
from tiltlock.enforcer import MockBitgetClient
from tiltlock.evolver import ChecklistEvolver
from tiltlock.models import TradeFill, OrderCancel, TiltTriggerEvent

console = Console()


def _merge_trigger(existing: TiltTriggerEvent | None, incoming: TiltTriggerEvent) -> TiltTriggerEvent:
    """Keeps latest metrics while accumulating episode signatures."""
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
    """Executes the complete deterministic demo sequence without network calls.

    Guaranteed to complete in < 60 seconds with exit code 0.
    Stage order: Detect → Diagnose → Enforce → Evolve.
    """
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

    enforcer.clear_lock()

    console.print()
    console.print(
        Panel.fit(
            "[bold white on blue] TILTLOCK: REVIEW & SELF-EVOLUTION ENGINE [/bold white on blue]\n"
            f"[dim]Account:[/dim] [bold]{fixture['trader_account']['account_id']}[/bold] "
            f"([green]${fixture['trader_account']['starting_balance_usdt']:,.2f} USDT[/green]) | "
            f"[dim]Active Rules:[/dim] [cyan]{len(checklist.rules)}[/cyan] | "
            "[dim]Mode:[/dim] [bold yellow]--demo (Zero-Network)[/bold yellow]",
            title="[bold cyan]Bitget Agentic Sub-Account Session[/bold cyan]",
            border_style="blue",
        )
    )

    rule_table = Table(title="Active Session Checklist (Pre-Session)", border_style="dim")
    rule_table.add_column("Rule ID", style="bold cyan", width=8)
    rule_table.add_column("Trigger Condition", style="yellow")
    rule_table.add_column("Hard Constraint", style="white")
    for r in checklist.rules:
        rule_table.add_row(r.rule_id, r.condition, r.hard_constraint)
    console.print(rule_table)
    console.print()

    delay = 0.8 / speed_multiplier if not auto_yes else 0.2
    console.print("[bold yellow]Ingesting Live Order Stream...[/bold yellow]\n")

    triggered_event: TiltTriggerEvent | None = None
    for item in fixture["timeline"]:
        time.sleep(delay)
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
            pnl_str = (
                f"[red]${fill.pnl:,.2f}[/red]"
                if fill.pnl < 0
                else f"[green]+${fill.pnl:,.2f}[/green]"
                if fill.pnl > 0
                else "[dim]$0.00[/dim]"
            )
            console.print(
                f"[bold cyan][T+{item['timestamp_offset_sec']:03d}s][/bold cyan] "
                f"[bold]{fill.side} {fill.size} {fill.symbol}[/bold] | "
                f"PnL: {pnl_str} | [dim]{fill.narrative}[/dim]"
            )
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
            console.print(
                f"[bold red][T+{item['timestamp_offset_sec']:03d}s] ORDER CANCEL:[/bold red] "
                f"[bold]{cancel.order_id} ({cancel.symbol})[/bold] @ ${cancel.price:.2f} | "
                f"Unrealized PnL: [red]${cancel.unrealized_pnl:.2f}[/red] | "
                f"[dim]{cancel.narrative}[/dim]"
            )

        if trigger is not None and trigger.is_triggered:
            triggered_event = _merge_trigger(triggered_event, trigger)

    console.print()
    if not triggered_event:
        console.print("[green]Session concluded without tilt triggers.[/green]")
        return 0

    # 1. DETECT
    console.print(
        Panel.fit(
            f"[bold red]CRITICAL BEHAVIORAL SIGNATURE DETECTED[/bold red]\n"
            f"[yellow]Signatures:[/yellow] {', '.join(triggered_event.signatures)}\n"
            f"[yellow]Cumulative Session Loss:[/yellow] "
            f"[red]${triggered_event.session_loss:,.2f}[/red] | "
            f"[yellow]Size Escalation:[/yellow] "
            f"[red]{triggered_event.size_ratio:.1f}x baseline[/red]",
            title="[bold red]DETECTOR ALERT[/bold red]",
            border_style="red",
        )
    )
    time.sleep(delay)

    # 2. DIAGNOSE
    console.print("[bold cyan]Invoking Cognitive Trade Diagnostics Engine...[/bold cyan]")
    diagnosis = diagnostician.diagnose(
        trigger=triggered_event,
        checklist=checklist,
        market_context=fixture.get("market_regime"),
    )

    diag_table = Table(title="Cognitive Tilt Diagnosis Report", border_style="cyan")
    diag_table.add_column("Diagnostic Field", style="bold yellow", width=22)
    diag_table.add_column("Clinical Analysis", style="white")
    diag_table.add_row(
        "Primary Pathology",
        f"[bold red]{diagnosis.pathology}[/bold red] (Confidence: {diagnosis.confidence:.0%})",
    )
    diag_table.add_row("Cognitive Distortion", diagnosis.cognitive_distortion)
    diag_table.add_row(
        "Violated Rule(s)",
        f"[bold red]{', '.join(diagnosis.violated_checklist_rules)}[/bold red]",
    )
    diag_table.add_row("Session PnL Cost", f"[red]-${diagnosis.session_cost:,.2f} USDT[/red]")
    diag_table.add_row("Sequence Audit", diagnosis.sequence_audit)
    diag_table.add_row("Prescribed Cooldown", f"{diagnosis.prescribed_cooldown_minutes} minutes")
    console.print(diag_table)
    console.print()
    time.sleep(delay)

    # 3. ENFORCE
    cooldown_minutes = max(
        cfg.cooldown.min_minutes,
        min(diagnosis.prescribed_cooldown_minutes, cfg.cooldown.max_minutes),
    )
    should_flatten = aggressive or cfg.policy.flatten_on_lock
    console.print("[bold yellow]Activating Bitget Agent Hub Live Enforcement...[/bold yellow]")
    canceled_orders = enforcer.cancel_all_orders("TSLAUSDT_rToken")
    canceled_strategies = enforcer.cancel_strategy_orders("TSLAUSDT_rToken")
    enforcer.set_leverage("TSLAUSDT_rToken", leverage=1)

    closed_msg = ""
    if should_flatten:
        enforcer.close_position("TSLAUSDT_rToken")
        closed_msg = (
            "\n• [bold]position --action close:[/bold] Flattened active position on "
            "[cyan]TSLAUSDT_rToken[/cyan]"
        )

    lock_state = enforcer.set_cooldown(
        minutes=cooldown_minutes,
        reason=triggered_event.summary,
        session_cost=triggered_event.session_loss,
    )

    console.print(
        Panel(
            f"[bold white on red] ACCOUNT IN COOLDOWN — {cooldown_minutes}:00 REMAINING "
            f"[/bold white on red]\n\n"
            f"• [bold]order --action cancelAll:[/bold] Canceled "
            f"[cyan]{len(canceled_orders)}[/cyan] active limit orders\n"
            f"• [bold]strategy_order --action open/cancel:[/bold] Canceled "
            f"[cyan]{len(canceled_strategies)}[/cyan] active stop triggers\n"
            f"• [bold]position --action setLeverage:[/bold] Dropped to [cyan]1x[/cyan] on "
            f"TSLAUSDT_rToken"
            f"{closed_msg}\n"
            f"• [bold]Local Gateway Freeze:[/bold] Locks active until "
            f"[yellow]{lock_state.unlocks_at}[/yellow]",
            title="[bold red]Enforcement Actions Applied (Agentic Sub-Account)[/bold red]",
            border_style="red",
        )
    )

    console.print("[dim]Simulating trader re-entry attempt during active cooldown...[/dim]")
    try:
        enforcer.place_order("TSLAUSDT_rToken", "BUY", 10.0, 240.0)
        console.print("[bold red]Unexpected: order was accepted during cooldown.[/bold red]")
    except PermissionError as pe:
        console.print(f"[bold red][X] [PERMISSION_DENIED][/bold red] Order rejected by TiltLock: {pe}\n")

    time.sleep(delay)

    # 4. EVOLVE
    auto_sec = 0 if auto_yes else cfg.policy.demo_auto_accept_seconds
    accepted, updated_checklist = evolver.evaluate_rule_proposal(
        rule=diagnosis.evolved_rule,
        auto_accept_seconds=auto_sec,
        auto_yes=auto_yes,
    )

    console.print()
    updated_table = Table(
        title=f"Evolved Trading Checklist (v{updated_checklist.version})",
        border_style="green",
    )
    updated_table.add_column("Rule ID", style="bold cyan", width=8)
    updated_table.add_column("Condition", style="yellow")
    updated_table.add_column("Hard Constraint", style="white")
    for r in updated_checklist.rules:
        updated_table.add_row(r.rule_id, r.condition, r.hard_constraint)
    console.print(updated_table)

    if accepted:
        console.print(
            f"[bold green][OK] Rule {diagnosis.evolved_rule.rule_id} accepted into live checklist."
            f"[/bold green]"
        )

    console.print()
    console.print(
        "[bold green][OK] TiltLock Demo completed successfully (Exit Code: 0).[/bold green]\n"
    )
    return 0
