"""Thin natural-language entry point over the existing TiltLock loop."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from tiltlock.display import print_checklist, print_diagnosis
from tiltlock.enforcer import get_bitget_client
from tiltlock.evolver import ChecklistEvolver
from tiltlock.models import TiltDiagnosis, EvolvedRule
from tiltlock.review_store import load_review

console = Console()


def interpret(question: str) -> str:
    q = question.lower().strip()
    if any(w in q for w in ("unlock", "clear lock", "release")):
        return "unlock"
    if any(w in q for w in ("demo", "show me", "run it", "simulate")):
        return "demo"
    if any(
        w in q
        for w in (
            "why",
            "review",
            "what happened",
            "tilt",
            "diagnos",
            "revenge",
        )
    ):
        return "review"
    if "lock" in q and "why" not in q and "unlock" not in q:
        if q.strip() in ("lock", "locked") or "status" in q:
            return "status"
    if any(w in q for w in ("status", "cooldown", "checklist")):
        return "status"
    return "help"


def cmd_ask(question: str) -> int:
    intent = interpret(question)
    if intent == "unlock":
        from tiltlock.cli import cmd_unlock

        return cmd_unlock()
    if intent == "status":
        from tiltlock.cli import cmd_status

        return cmd_status()
    if intent == "demo":
        from tiltlock.demo_runner import run_demo

        return run_demo(auto_yes=True)
    if intent == "review":
        return _print_last_review()
    console.print(
        Panel(
            "I can review the last tilt lock, show status, unlock, or run the demo.\n\n"
            "Try:\n"
            "  [cyan]python -m tiltlock.cli ask \"why did I get locked?\"[/cyan]\n"
            "  [cyan]python -m tiltlock.cli ask \"run the demo\"[/cyan]\n"
            "  [cyan]python -m tiltlock.cli ask \"status\"[/cyan]",
            title="TiltLock ask",
            border_style="cyan",
        )
    )
    return 0


def _print_last_review() -> int:
    data = load_review()
    client = get_bitget_client("demo")
    is_locked, state = client.check_lock()
    checklist = ChecklistEvolver().load_checklist()

    if not data:
        console.print(
            "[yellow]No saved review yet. Run the demo first:[/yellow] "
            "[cyan]python -m tiltlock.cli run --demo --yes[/cyan]"
        )
        return 0

    diagnosis = TiltDiagnosis(
        pathology=data.get("pathology", "UNKNOWN"),
        confidence=float(data.get("confidence", 0.0)),
        violated_checklist_rules=data.get("violated_checklist_rules") or [],
        sequence_audit=data.get("sequence_audit", ""),
        cognitive_distortion=data.get("cognitive_distortion", ""),
        session_cost=float(data.get("session_cost", 0.0)),
        prescribed_cooldown_minutes=int(data.get("prescribed_cooldown_minutes", 45)),
        evolved_rule=EvolvedRule(**data["evolved_rule"])
        if data.get("evolved_rule")
        else EvolvedRule(
            rule_id="R00",
            condition="n/a",
            hard_constraint="n/a",
            rationale="n/a",
        ),
    )
    lock_line = "Cooldown is active." if is_locked else "No active cooldown."
    if is_locked and state:
        lock_line = f"Cooldown until {state.unlocks_at}. Reason: {state.reason}"
    console.print(Panel(lock_line, title="Answer", border_style="red" if is_locked else "green"))
    print_diagnosis(diagnosis)
    print_checklist(checklist, f"Checklist v{checklist.version}")
    return 0
