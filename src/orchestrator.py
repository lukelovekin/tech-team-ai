"""
Full pipeline orchestrator: plan → dev → review → qa → audit.
Each agent receives the previous agent's output as context.
"""

from pathlib import Path

from rich.console import Console
from rich.rule import Rule

from src import context
from src.agents.architect import ArchitectAgent
from src.agents.developer import DeveloperAgent
from src.agents.qa import QAAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.security import SecurityAgent
from src.config import Settings

console = Console()


class PipelineResult:
    def __init__(self) -> None:
        self.plan: str = ""
        self.implementation: str = ""
        self.review: str = ""
        self.tests: str = ""
        self.audit: str = ""

    def to_markdown(self, task: str) -> str:
        sections = [f"# tech-team pipeline report\n\n**Task:** {task}\n"]
        if self.plan:
            sections.append(f"## Architecture plan\n\n{self.plan}")
        if self.implementation:
            sections.append(f"## Implementation\n\n{self.implementation}")
        if self.review:
            sections.append(f"## Code review\n\n{self.review}")
        if self.tests:
            sections.append(f"## Test coverage\n\n{self.tests}")
        if self.audit:
            sections.append(f"## Security audit\n\n{self.audit}")
        return "\n\n---\n\n".join(sections)


def run_pipeline(
    task: str,
    settings: Settings,
    repo_path: Path,
    skip_plan: bool = False,
    skip_qa: bool = False,
    skip_audit: bool = False,
    write_report: bool = True,
) -> PipelineResult:
    project_context = context.gather(repo_path)
    result = PipelineResult()

    # 1. Architect: plan
    if not skip_plan:
        _header("Architect — planning implementation")
        architect = ArchitectAgent(settings, repo_path)
        result.plan = architect.run(
            f"Plan the implementation of the following task:\n\n{task}",
            extra_context=project_context,
        )

    # 2. Developer: implement
    _header("Developer — implementing")
    dev_task = task
    if result.plan:
        dev_task = (
            f"Implement the following task. An architecture plan has been prepared — follow it:\n\n"
            f"## Task\n{task}\n\n## Architecture plan\n{result.plan}"
        )
    developer = DeveloperAgent(settings, repo_path)
    result.implementation = developer.run(dev_task, extra_context=project_context)

    # 3. Reviewer: review
    _header("Reviewer — reviewing changes")
    reviewer = ReviewerAgent(settings, repo_path)
    result.review = reviewer.run(
        f"Review the changes just made for the following task:\n\n{task}\n\n"
        f"Implementation summary from developer:\n{result.implementation}",
        extra_context=project_context,
    )

    # 4. QA: tests
    if not skip_qa:
        _header("QA — writing tests")
        qa = QAAgent(settings, repo_path)
        result.tests = qa.run(
            f"Add or improve tests for the changes just made:\n\n{task}\n\n"
            f"Implementation summary:\n{result.implementation}",
            extra_context=project_context,
        )

    # 5. Security: audit
    if not skip_audit:
        _header("Security — auditing")
        security = SecurityAgent(settings, repo_path)
        result.audit = security.run(
            f"Audit the changes just made for security issues:\n\n{task}",
            extra_context=project_context,
        )

    if write_report:
        report_path = repo_path / "briefing" / "brief.md"
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(result.to_markdown(task), encoding="utf-8")
        console.print(f"\n[green]Session brief written to {report_path}[/green]")

    return result


def _header(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]", style="cyan"))
    console.print()
