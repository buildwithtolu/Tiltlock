"""Command Line Interface for TiltLock."""

import argparse
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from tiltlock.demo_runner import run_demo
from tiltlock.paper_runner import run_paper
from tiltlock.enforcer import get_bitget_client
from tiltlock.evolver import ChecklistEvolver

console = Console()


def cmd_status() -> int:
    """Displays current lock status, cooldown remaining, and active checklist."""
    evolver = ChecklistEvolver()
    checklist = evolver.load_checklist()
    client = get_bitget_client("demo")
    is_locked, state = client.check_lock()

    console.print()
    if is_locked and state:
        console.print(
            Panel(
                f"[bold red]ACCOUNT IN COOLDOWN[/bold red]\n"
                f"[yellow]Locked At:[/yellow] {state.locked_at}\n"
                f"[yellow]Unlocks At:[/yellow] {state.unlocks_at}\n"
                f"[yellow]Reason:[/yellow] {state.reason}\n"
                f"[yellow]Session Loss:[/yellow] ${state.session_cost:,.2f} USDT",
                title="TiltLock Status",
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]ACCOUNT ACTIVE & UNRESTRICTED[/bold green]\n"
                "No active cooldown lock. Execution routes open.",
                title="TiltLock Status",
                border_style="green",
            )
        )

    # Show active checklist
    table = Table(title=f"Active Rule Checklist (v{checklist.version})", border_style="cyan")
    table.add_column("Rule ID", style="bold cyan", width=8)
    table.add_column("Condition", style="yellow")
    table.add_column("Hard Constraint", style="white")
    for r in checklist.rules:
        table.add_row(r.rule_id, r.condition, r.hard_constraint)
    console.print(table)
    console.print()
    return 0


def cmd_unlock() -> int:
    """Manual emergency lockfile clearer."""
    client = get_bitget_client("demo")
    client.clear_lock()
    console.print("[bold green][OK] Cooldown lock cleared. Account unlocked.[/bold green]")
    return 0


def cmd_run(args) -> int:
    """Dispatches execution based on selected mode."""
    if args.fixture and not args.paper:
        console.print("[red]Error: --fixture only applies with --paper.[/red]")
        return 1
    if args.demo:
        return run_demo(auto_yes=args.yes, aggressive=args.aggressive)
    elif args.paper:
        return run_paper(auto_yes=args.yes, aggressive=args.aggressive, use_fixture=args.fixture)
    elif args.live:
        if not args.yes:
            confirm = input(
                "WARNING: --live mode will enforce restrictions on your REAL sub-account. Proceed? [y/N]: "
            )
            if confirm.strip().lower() != "y":
                console.print("[yellow]Aborted live mode.[/yellow]")
                return 1
        console.print(
            Panel(
                "[bold red]--live mode is intentionally gated for week-1.[/bold red]\n\n"
                "Adapters exist ([bold]BgcCliBitgetClient[/bold]), but live enforcement is out of "
                "the demo critical path. Use [cyan]--demo[/cyan] for judge recordings.",
                title="TiltLock Live Mode",
                border_style="red",
            )
        )
        return 0
    else:
        console.print("[red]Error: Specify one of --demo, --paper, or --live.[/red]")
        return 1


def main():
    parser = argparse.ArgumentParser(
        prog="tiltlock",
        description="Autonomous trade review, tilt diagnosis, and self-evolving checklist system.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Start TiltLock engine")
    run_group = run_parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--demo", action="store_true", help="Zero-network deterministic recording demo")
    run_group.add_argument("--paper", action="store_true", help="Live poll fills via Bitget Agent Hub CLI ('bgc')")
    run_group.add_argument("--live", action="store_true", help="Connect to Bitget production sub-account")
    run_parser.add_argument("--fixture", action="store_true", help="Replay deterministic fixture through paper adapter (--paper only)")
    run_parser.add_argument("--yes", "-y", action="store_true", help="Auto-accept all interactive prompts")
    run_parser.add_argument("--aggressive", action="store_true", help="Aggressive flatten: close open positions upon tilt lock")

    # status command
    subparsers.add_parser("status", help="Show current cooldown and checklist status")

    # unlock command
    subparsers.add_parser("unlock", help="Emergency reset of local cooldown lock")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(args))
    elif args.command == "status":
        sys.exit(cmd_status())
    elif args.command == "unlock":
        sys.exit(cmd_unlock())


if __name__ == "__main__":
    main()
