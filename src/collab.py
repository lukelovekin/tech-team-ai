"""
Collaborative agent loop.

Agents iterate on each other's output until all are satisfied (no CRITICAL/WARNING
findings), then the user sees the full diff and confirms before any changes are kept.

Flow:
  1. Architect plans (once, before any code is written)
  2. User confirms the plan — bail out here with zero file changes
  3. Loop up to max_rounds:
       a. Developer writes / revises code
       b. Show running diff
       c. Reviewer, QA, Security analyse
       d. If no CRITICAL/WARNING → break
       e. Summarise issues, pass to Developer for next round
  4. Show final diff
  5. User confirms → changes stay in working tree (commit normally)
               deny → all changes reverted to original state
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import typer
from rich.console import Console
from rich.rule import Rule
from rich.syntax import Syntax

from src import context
from src.agents.architect import ArchitectAgent
from src.agents.developer import DeveloperAgent
from src.agents.qa import QAAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.security import SecurityAgent
from src.config import Settings

console = Console()


def run_collab(
    task: str,
    settings: Settings,
    repo_path: Path,
    max_rounds: int = 5,
    skip_plan: bool = False,
    skip_qa: bool = False,
    skip_audit: bool = False,
) -> bool:
    """
    Run the collaborative loop. Returns True if changes were applied, False if reverted.
    """
    project_ctx = context.gather(repo_path)

    # Record state before we touch anything so we can cleanly revert.
    original_tracked_diff = _git(repo_path, ["git", "diff"])
    original_untracked = set(_get_untracked_files(repo_path))

    dirty = original_tracked_diff or original_untracked
    if dirty:
        console.print("[yellow]Working tree has uncommitted changes.[/yellow]")
        console.print("[dim]If you reject the final result, only changes made during this session will be reverted.[/dim]")
        if not typer.confirm("Continue?", default=False):
            return False

    plan = ""

    # -------------------------------------------------------------------------
    # Step 1: Architect plans — no files written yet
    # -------------------------------------------------------------------------
    if not skip_plan:
        console.print(Rule("[cyan]Architect — planning[/cyan]", style="dim"))
        plan = ArchitectAgent(settings, repo_path).run(
            f"Plan the implementation of: {task}",
            extra_context=project_ctx,
        )
        # Re-gather now that architect has written briefing/context.md —
        # all subsequent agents get the structured handoff automatically.
        project_ctx = context.gather(repo_path)
        console.print()
        if not typer.confirm("Proceed with implementation?", default=True):
            console.print("[dim]Aborted — no files changed.[/dim]")
            return False

    # Snapshot untracked files right before developer starts writing.
    pre_dev_untracked = set(_get_untracked_files(repo_path))

    previous_findings = ""
    last_review = ""
    last_qa_out = ""
    last_audit_out = ""

    # -------------------------------------------------------------------------
    # Steps 2–N: Developer → Reviewer / QA / Security loop
    # -------------------------------------------------------------------------
    for round_num in range(1, max_rounds + 1):
        console.print()
        console.print(Rule(f"[bold cyan]Round {round_num} / {max_rounds}[/bold cyan]", style="cyan"))
        console.print()

        # --- Developer ---
        console.print(Rule("[cyan]Developer[/cyan]", style="dim"))
        if round_num == 1:
            dev_task = (
                f"Implement the following task. Follow the architecture plan:\n\n"
                f"## Task\n{task}\n\n## Architecture plan\n{plan}"
                if plan
                else task
            )
        else:
            dev_task = (
                f"Fix the issues identified in round {round_num - 1}.\n\n"
                f"## Original task\n{task}\n\n"
                f"## Issues to resolve\n{previous_findings}"
            )

        DeveloperAgent(settings, repo_path).run(dev_task, extra_context=project_ctx)

        show_diff(repo_path, f"Changes after round {round_num}")

        # --- Analysis agents ---
        round_findings: list[str] = []
        combined = ""

        # Reviewer always runs first, with streaming.
        console.print(Rule("[cyan]Reviewer[/cyan]", style="dim"))
        review_out = ReviewerAgent(settings, repo_path, model=settings.analysis_model).run(
            f"Review changes made for: {task}. Use get_git_diff to see what changed.",
            extra_context=project_ctx,
        )
        round_findings.append(f"## Code Review\n{review_out}")
        combined += review_out
        last_review = review_out

        # QA + Security only run when the reviewer is satisfied OR we're at max rounds.
        # Skipping them on intermediate rounds saves 10–15 min per build.
        reviewer_clean = count_issues(review_out) == (0, 0)
        is_last_round = round_num == max_rounds
        run_full_analysis = reviewer_clean or is_last_round

        if run_full_analysis:
            # Run QA and Security in parallel (no streaming — outputs printed after).
            parallel_tasks: dict[str, object] = {}
            with ThreadPoolExecutor(max_workers=2) as pool:
                if not skip_qa:
                    parallel_tasks["qa"] = pool.submit(
                        QAAgent(settings, repo_path, model=settings.analysis_model).run,
                        f"Check test coverage for changes made for: {task}",
                        project_ctx,
                        False,
                    )
                if not skip_audit:
                    parallel_tasks["audit"] = pool.submit(
                        SecurityAgent(settings, repo_path, model=settings.analysis_model).run,
                        f"Audit changes made for: {task}. Use get_git_diff to see what changed.",
                        project_ctx,
                        False,
                    )

            if "qa" in parallel_tasks:
                qa_out = parallel_tasks["qa"].result()  # type: ignore[union-attr]
                console.print(Rule("[cyan]QA[/cyan]", style="dim"))
                console.print(qa_out)
                round_findings.append(f"## QA\n{qa_out}")
                combined += qa_out
                last_qa_out = qa_out

            if "audit" in parallel_tasks:
                audit_out = parallel_tasks["audit"].result()  # type: ignore[union-attr]
                console.print(Rule("[cyan]Security[/cyan]", style="dim"))
                console.print(audit_out)
                round_findings.append(f"## Security\n{audit_out}")
                combined += audit_out
                last_audit_out = audit_out

        criticals, warnings = count_issues(combined)

        console.print()
        if criticals == 0 and warnings == 0:
            console.print(f"[bold green]All agents satisfied after round {round_num}.[/bold green]")
            break

        summary_parts: list[str] = []
        if criticals:
            summary_parts.append(f"[red]{criticals} critical[/red]")
        if warnings:
            summary_parts.append(f"[yellow]{warnings} warning(s)[/yellow]")
        console.print(f"Round {round_num} complete — {', '.join(summary_parts)} found.")

        if round_num == max_rounds:
            console.print(f"[yellow]Max rounds ({max_rounds}) reached.[/yellow]")
            break

        previous_findings = "\n\n".join(round_findings)
        console.print("[dim]Passing findings to developer for next round...[/dim]")

    # -------------------------------------------------------------------------
    # Final confirmation — show complete diff, let user decide
    # -------------------------------------------------------------------------
    console.print()
    console.print(Rule("[bold cyan]Proposed changes[/bold cyan]", style="cyan"))
    show_diff(repo_path, "All changes this session")
    console.print()

    if typer.confirm("Apply these changes?", default=True):
        _write_brief(repo_path, task, plan, last_review, last_qa_out, last_audit_out)
        console.print("[green]Changes applied. Review and commit when ready.[/green]")
        return True

    # Revert: restore tracked files, remove any new untracked files the agents created.
    _git(repo_path, ["git", "checkout", "."])
    new_files = set(_get_untracked_files(repo_path)) - original_untracked
    for rel in new_files:
        path = repo_path / rel
        if path.exists():
            path.unlink()
    console.print("[dim]Changes reverted.[/dim]")
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_brief(
    repo_path: Path,
    task: str,
    plan: str,
    review: str,
    qa: str,
    audit: str,
) -> None:
    sections = [f"# tech-team session brief\n\n**Task:** {task}"]
    if plan:
        sections.append(f"## Architecture plan\n\n{plan}")
    if review:
        sections.append(f"## Code review\n\n{review}")
    if qa:
        sections.append(f"## QA\n\n{qa}")
    if audit:
        sections.append(f"## Security audit\n\n{audit}")
    brief_path = repo_path / "briefing" / "brief.md"
    brief_path.parent.mkdir(exist_ok=True)
    brief_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
    console.print(f"[dim]Session brief written to {brief_path}[/dim]")


def show_diff(repo_path: Path, label: str) -> None:
    diff = _git(repo_path, ["git", "diff"])
    console.print()
    console.print(Rule(f"[dim]{label}[/dim]", style="dim"))
    if diff:
        if len(diff) > 10_000:
            diff = diff[:10_000] + "\n... (diff truncated — use git diff for the full output)"
        console.print(Syntax(diff, "diff", theme="monokai", word_wrap=True))
    else:
        console.print("[dim](no tracked file changes yet)[/dim]")
    console.print()


def count_issues(text: str) -> tuple[int, int]:
    upper = text.upper()
    return upper.count("[CRITICAL]"), upper.count("[WARNING]")


def _get_untracked_files(repo_path: Path) -> list[str]:
    out = _git(repo_path, ["git", "ls-files", "--others", "--exclude-standard"])
    return [f for f in out.splitlines() if f]


def _git(repo_path: Path, cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(repo_path), timeout=30
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""
