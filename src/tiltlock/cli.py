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
from tiltlock.demo_runner import run_demo
from tiltlock.display import print_checklist
from tiltlock.paper_runner import run_paper
from tiltlock.enforcer import get_bitget_client
from tiltlock.evolver import ChecklistEvolver

console = Console()


def cmd_status() -> int:
    """Show cooldown lock status and the active checklist."""
    evolver = ChecklistEvolver()
    checklist = evolver.load_checklist()
    client = get_bitget_client("demo")
    is_locked, state = client.check_lock()

    console.print()
    if is_locked and state:
        console.print(
            Panel(
                f"[bold red]COOLDOWN ACTIVE[/bold red]\n"
                f"Locked at: {state.locked_at}\n"
                f"Unlocks at: {state.unlocks_at}\n"
                f"Reason: {state.reason}\n"
                f"Session loss: ${state.session_cost:,.2f} USDT",
                title="TiltLock Status",
                border_style="red",
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]No active cooldown[/bold green]\n"
                "New orders are allowed by this local TiltLock gateway.\n"
                "[dim]Note: cooldown is local to this tool, not an exchange-wide freeze.[/dim]",
                title="TiltLock Status",
                border_style="green",
            )
        )

    print_checklist(checklist, f"Active checklist (v{checklist.version})")
    console.print()
    return 0


def cmd_unlock() -> int:
    """Clear the local cooldown lockfile."""
    client = get_bitget_client("demo")
    client.clear_lock()
    console.print("[bold green][OK] Cooldown cleared. Trading gateway unlocked.[/bold green]")
    return 0


def cmd_run(args) -> int:
    """Dispatch run modes."""
    if args.fixture and not args.paper:
        console.print("[red]Error: --fixture only works with --paper.[/red]")
        return 1
    if args.demo:
        return run_demo(auto_yes=args.yes, aggressive=args.aggressive)
    if args.paper:
        return run_paper(
            auto_yes=args.yes,
            aggressive=args.aggressive,
            use_fixture=args.fixture,
            allow_writes=bool(args.yes or args.i_understand),
        )
    console.print("[red]Error: choose --demo or --paper.[/red]")
    return 1


def main():
    parser = argparse.ArgumentParser(
        prog="tiltlock",
        description=(
            "TiltLock detects revenge-trading patterns, pauses the account, "
            "and updates your personal trading rules."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run TiltLock")
    run_group = run_parser.add_mutually_exclusive_group(required=True)
    run_group.add_argument(
        "--demo",
        action="store_true",
        help="Offline demo with a built-in tilt scenario (no Bitget account needed)",
    )
    run_group.add_argument(
        "--paper",
        action="store_true",
        help="Use Bitget Demo Trading through the bgc CLI",
    )
    run_parser.add_argument(
        "--fixture",
        action="store_true",
        help="With --paper: replay the demo scenario through real bgc commands",
    )
    run_parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-accept checklist updates; for --paper also consents to Demo Trading write actions",
    )
    run_parser.add_argument(
        "--i-understand",
        dest="i_understand",
        action="store_true",
        help="Consent to Bitget Demo Trading write actions (cancel/leverage/close) without auto-accepting rules",
    )
    run_parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Also flatten open positions when locking the account",
    )

    subparsers.add_parser("status", help="Show cooldown and checklist")
    subparsers.add_parser("unlock", help="Clear the local cooldown lock")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(cmd_run(args))
    if args.command == "status":
        sys.exit(cmd_status())
    if args.command == "unlock":
        sys.exit(cmd_unlock())


if __name__ == "__main__":
    main()
