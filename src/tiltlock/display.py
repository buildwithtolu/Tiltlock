"""Shared terminal display helpers for consistent, plain-language output."""

from rich.console import Console
from rich.table import Table
from tiltlock.models import TiltDiagnosis, Checklist

console = Console()


def print_checklist(checklist: Checklist, title: str) -> None:
    table = Table(title=title, border_style="cyan")
    table.add_column("ID", style="bold cyan", width=8)
    table.add_column("When", style="yellow")
    table.add_column("Constraint", style="white")
    for rule in checklist.rules:
        table.add_row(rule.rule_id, rule.condition, rule.hard_constraint)
    console.print(table)


def print_diagnosis(diagnosis: TiltDiagnosis) -> None:
    table = Table(title="Trade Review", border_style="cyan")
    table.add_column("Field", style="bold yellow", width=18)
    table.add_column("Detail", style="white")
    table.add_row(
        "Pattern",
        f"[bold red]{diagnosis.pathology}[/bold red] ({diagnosis.confidence:.0%} confidence)",
    )
    table.add_row("Why it happened", diagnosis.cognitive_distortion)
    table.add_row(
        "Rules broken",
        ", ".join(diagnosis.violated_checklist_rules) or "None matched",
    )
    table.add_row("Session loss", f"[red]-${diagnosis.session_cost:,.2f} USDT[/red]")
    table.add_row("What happened", diagnosis.sequence_audit)
    table.add_row("Cooldown", f"{diagnosis.prescribed_cooldown_minutes} minutes")
    console.print(table)
