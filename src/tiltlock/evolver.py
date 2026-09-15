"""Dynamic checklist self-evolution engine with human-in-the-loop gate."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional
from rich.console import Console
from rich.panel import Panel
from tiltlock.config import AppConfig
from tiltlock.models import Checklist, EvolvedRule

logger = logging.getLogger("tiltlock.evolver")
console = Console()


class ChecklistEvolver:
    """Manages persistent personal rule checklists and the Track 3 human gate."""

    def __init__(self, checklist_path: Optional[Path] = None):
        root = AppConfig.find_repo_root()
        self.state_dir = root / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.checklist_path = checklist_path or (self.state_dir / "checklist.json")
        self.log_path = self.state_dir / "proposed_rules.log"

    @staticmethod
    def baseline_checklist() -> Checklist:
        """Returns the deterministic pre-session baseline (R01 + R02)."""
        return Checklist(
            version=1,
            rules=[
                EvolvedRule(
                    rule_id="R01",
                    condition="High-impact macro data releases (CPI, FOMC, NFP)",
                    hard_constraint="No new market or limit entries within 5 minutes before/after event",
                    rationale="Slippage spike and erratic spread expansion during high volatility events",
                    created_at="2026-09-11T12:00:00Z",
                ),
                EvolvedRule(
                    rule_id="R02",
                    condition="Tokenized equity (rToken) intraday trading",
                    hard_constraint="Maximum position sizing capped at 15 contracts per trade",
                    rationale="Prevents overleveraging in thin off-market order books",
                    created_at="2026-09-11T12:00:00Z",
                ),
            ],
        )

    def reset_to_baseline(self) -> Checklist:
        """Resets checklist to R01/R02 so --demo stays deterministic across runs."""
        checklist = self.baseline_checklist()
        self.save_checklist(checklist)
        return checklist

    def load_checklist(self) -> Checklist:
        """Loads the active rule checklist from disk."""
        if not self.checklist_path.exists():
            default_checklist = self.baseline_checklist()
            self.save_checklist(default_checklist)
            return default_checklist

        with open(self.checklist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Checklist(**data)

    def save_checklist(self, checklist: Checklist) -> None:
        """Saves the updated rule checklist to disk."""
        checklist.updated_at = datetime.utcnow().isoformat() + "Z"
        with open(self.checklist_path, "w", encoding="utf-8") as f:
            f.write(checklist.model_dump_json(indent=2))

    def evaluate_rule_proposal(
        self,
        rule: EvolvedRule,
        auto_accept_seconds: int = 3,
        auto_yes: bool = False,
    ) -> Tuple[bool, Checklist]:
        """Presents proposed rule to user gate and updates persistent state."""
        checklist = self.load_checklist()

        # Skip exact duplicate constraints already on the live checklist
        existing_constraints = {r.hard_constraint.strip().lower() for r in checklist.rules}
        if rule.hard_constraint.strip().lower() in existing_constraints:
            console.print(
                "[yellow]Proposed constraint already exists on the live checklist. "
                "Skipping duplicate append.[/yellow]"
            )
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.utcnow().isoformat()}Z] [DUPLICATE_SKIPPED] "
                    f"[{rule.rule_id}] {rule.hard_constraint}\n"
                )
            return False, checklist

        # Deduplicate rule_id
        existing_ids = {r.rule_id for r in checklist.rules}
        if rule.rule_id in existing_ids:
            next_num = len(checklist.rules) + 1
            rule.rule_id = f"R{next_num:02d}"

        rule.created_at = datetime.utcnow().isoformat() + "Z"

        console.print(
            Panel.fit(
                f"[bold]Proposed rule: {rule.rule_id}[/bold]\n"
                f"When: {rule.condition}\n"
                f"Rule: {rule.hard_constraint}\n"
                f"Why: {rule.rationale}",
                title="Update checklist?",
                border_style="cyan",
            )
        )

        accepted = False
        if auto_yes:
            console.print("[dim]Accepted automatically (--yes).[/dim]")
            accepted = True
        elif auto_accept_seconds > 0:
            console.print(
                f"[bold yellow]Add this rule to your checklist? [Y/n] "
                f"(auto-accept in {auto_accept_seconds}s)[/bold yellow]"
            )
            time.sleep(min(auto_accept_seconds, 3))
            accepted = True
            console.print("[green][OK] Rule added.[/green]")
        else:
            choice = input("Add this rule to your checklist? [Y/n]: ").strip().lower()
            accepted = choice in ["y", "yes", ""]

        # Update logs
        timestamp = datetime.utcnow().isoformat() + "Z"
        status = "ACCEPTED" if accepted else "REJECTED"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{status}] [{rule.rule_id}] {rule.hard_constraint}\n")

        if accepted:
            checklist.rules.append(rule)
            checklist.version += 1
            self.save_checklist(checklist)

        return accepted, checklist
