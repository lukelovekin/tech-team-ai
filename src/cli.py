"""tech-team CLI — invoke AI specialist agents from any repository."""

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.rule import Rule

from src import context
from src.agents.architect import ArchitectAgent
from src.agents.developer import DeveloperAgent
from src.agents.qa import QAAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.security import SecurityAgent
from src.config import Settings, find_repo_root, read_global_key, write_global_key, GLOBAL_CONFIG_FILE
from src.orchestrator import run_pipeline
from src.collab import run_collab, show_diff, count_issues

app = typer.Typer(
    name="tech-team",
    help="AI software team. Run specialist agents on any repo.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()

RepoOption = Annotated[
    Path,
    typer.Option("--repo", "-r", help="Target repo path. Defaults to nearest git root or cwd."),
]


def _resolve_repo(repo: Path) -> Path:
    if repo != Path("."):
        return repo.resolve()
    return find_repo_root()


def _banner(agent_name: str, repo_path: Path) -> None:
    console.print(Rule(f"[bold cyan]tech-team / {agent_name}[/bold cyan]", style="cyan"))
    console.print(f"[dim]repo: {repo_path}[/dim]\n")


def _load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as e:
        console.print(f"[red]Config error:[/red] {e}")
        console.print("[dim]Run [bold]tech-team setup[/bold] to save your Anthropic API key.[/dim]")
        console.print("[dim]Get a key at https://console.anthropic.com[/dim]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@app.command()
def setup() -> None:
    """First-time setup: save your Anthropic API key globally.

    \b
    Stores the key in ~/.config/tech-team/config (chmod 600) so it works
    from any repo without per-project .env files.

    \b
    Get a key at: https://console.anthropic.com
    Pricing:      https://anthropic.com/pricing  (you pay Anthropic directly)
    """
    console.print()
    console.print(Rule("[bold cyan]tech-team setup[/bold cyan]", style="cyan"))
    console.print()

    existing = read_global_key()
    if existing:
        masked = existing[:8] + "..." + existing[-4:]
        console.print(f"[dim]Current key: {masked}[/dim]")
        if not typer.confirm("Replace existing key?", default=False):
            console.print("[dim]No changes made.[/dim]")
            raise typer.Exit(0)

    console.print("  Get your API key at [cyan]https://console.anthropic.com[/cyan]")
    console.print("  You are billed directly by Anthropic based on usage.")
    console.print("  Prompt caching is enabled — repeated runs cost significantly less.")
    console.print()

    api_key = typer.prompt("Anthropic API key", hide_input=True)
    api_key = api_key.strip()

    if not api_key.startswith("sk-ant-"):
        console.print("[yellow]Warning: key doesn't look like an Anthropic key (expected sk-ant-...).[/yellow]")
        if not typer.confirm("Save it anyway?", default=False):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(1)

    write_global_key(api_key)
    console.print()
    console.print(f"[green]Key saved to {GLOBAL_CONFIG_FILE}[/green]")
    console.print("[dim]You're all set. Try: tech-team review[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """Check your setup — Python version, API key, git, and dependencies."""
    import subprocess as sp
    import sys
    import anthropic as ant

    console.print()
    console.print(Rule("[bold cyan]tech-team doctor[/bold cyan]", style="cyan"))
    console.print()

    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
        line = f"  {icon}  {label}"
        if detail:
            line += f"  [dim]{detail}[/dim]"
        console.print(line)
        if not passed:
            ok = False

    # Python version
    major, minor = sys.version_info[:2]
    check(
        f"Python {major}.{minor}",
        major == 3 and minor >= 11,
        "" if minor >= 11 else "Python 3.11+ required — run: brew install python@3.12",
    )

    # Git
    git_result = sp.run(["git", "--version"], capture_output=True, text=True)
    check("git", git_result.returncode == 0, git_result.stdout.strip())

    # API key present
    api_key = read_global_key()
    if not api_key:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    key_present = bool(api_key)
    check(
        "API key configured",
        key_present,
        "run: tech-team setup" if not key_present else f"{api_key[:8]}...{api_key[-4:]}",
    )

    # API key valid (live check)
    if key_present:
        try:
            client = ant.Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            check("API key valid", True, "connection successful")
        except ant.AuthenticationError:
            check("API key valid", False, "key rejected — check console.anthropic.com")
        except ant.APIError as e:
            check("API key valid", False, f"API error: {e}")

    console.print()
    if ok:
        console.print("[bold green]Everything looks good.[/bold green]")
    else:
        console.print("[yellow]Fix the issues above, then re-run tech-team doctor.[/yellow]")
    console.print()


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


_INIT_SYSTEM_PROMPT = """\
You are a technical writer generating a CLAUDE.md file for a software project.
CLAUDE.md is read by AI coding agents to understand a codebase before they touch it.
A great CLAUDE.md is concise, factual, and tells an agent exactly what it needs to know
to write code that fits the existing patterns — without reading every file first.

Output only the raw Markdown content of CLAUDE.md. No explanation, no code fences around
the whole thing, no preamble. Start with # <project name>.
"""


@app.command()
def init(
    repo: RepoOption = Path("."),
) -> None:
    """Generate a CLAUDE.md for any repo so agents start with full context.

    \b
    Reads your project structure, stack, and key files, then writes a
    CLAUDE.md that tells agents how your codebase works before they touch it.
    Saves re-exploration time on every agent run.

    \b
    Examples:
      tech-team init                     # current directory
      tech-team init --repo ~/my-project
    """
    import anthropic as ant

    repo_path = _resolve_repo(repo)
    settings = _load_settings()

    claude_md = repo_path / "CLAUDE.md"
    if claude_md.exists():
        console.print(f"[yellow]CLAUDE.md already exists at {claude_md}[/yellow]")
        if not typer.confirm("Overwrite?", default=False):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    _banner("Init", repo_path)
    console.print("[dim]Reading project structure...[/dim]")

    project_ctx = context.gather(repo_path)

    console.print("[dim]Generating CLAUDE.md...[/dim]\n")

    client = ant.Anthropic(api_key=settings.anthropic_api_key)
    with client.messages.stream(
        model=settings.model,
        max_tokens=2048,
        system=_INIT_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Generate a CLAUDE.md for this project.\n\n{project_ctx}\n\n"
                "Cover: what the project is, the tech stack, repo layout, key conventions, "
                "how to run it locally, and anything an AI agent must know before editing code."
            ),
        }],
    ) as s:
        content = ""
        for text in s.text_stream:
            console.print(text, end="")
            content += text
        console.print()

    claude_md.write_text(content, encoding="utf-8")
    console.print(f"\n[green]Written: {claude_md}[/green]")
    console.print("[dim]Commit this file so agents are pre-oriented on every run.[/dim]")


# ---------------------------------------------------------------------------
# Individual agent commands
# ---------------------------------------------------------------------------


@app.command()
def dev(
    task: Annotated[str, typer.Argument(help="What to implement. Can be a prompt or ticket description.")],
    repo: RepoOption = Path("."),
    plan: Annotated[bool, typer.Option("--plan", help="Run architect first to plan before implementing.")] = False,
) -> None:
    """Developer agent: implement features and fixes from a prompt.

    Use --plan to run the architect agent first. The architect produces a structured
    implementation plan which the developer then follows. Good for non-trivial changes.
    For a full iterative loop with review, use: tech-team collab
    """
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    ctx = context.gather(repo_path)

    arch_plan = ""
    if plan:
        _banner("Architect", repo_path)
        arch_plan = ArchitectAgent(settings, repo_path).run(
            f"Plan the implementation of: {task}", extra_context=ctx
        )
        console.print()
        if not typer.confirm("Proceed with implementation?", default=True):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    _banner("Developer", repo_path)
    dev_task = (
        f"Implement the following task. Follow the architecture plan:\n\n"
        f"## Task\n{task}\n\n## Architecture plan\n{arch_plan}"
        if arch_plan
        else task
    )
    DeveloperAgent(settings, repo_path).run(dev_task, extra_context=ctx)


@app.command()
def review(
    path: Annotated[str, typer.Argument(help="File or directory to review. Defaults to staged diff.")] = ".",
    staged: Annotated[bool, typer.Option("--staged", help="Review only staged changes.")] = False,
    repo: RepoOption = Path("."),
) -> None:
    """Reviewer agent: code quality, pattern consistency, regression risk."""
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    _banner("Reviewer", repo_path)
    ctx = context.gather(repo_path)
    task = (
        f"Review the staged changes in this repository."
        if staged
        else f"Review the code in: {path}"
    )
    if staged:
        task += " Use get_git_diff with staged=true to see what's staged."
    ReviewerAgent(settings, repo_path).run(task, extra_context=ctx)


@app.command()
def qa(
    path: Annotated[str, typer.Argument(help="File or directory to write tests for.")] = ".",
    repo: RepoOption = Path("."),
) -> None:
    """QA agent: write and improve tests, ensure meaningful coverage."""
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    _banner("QA", repo_path)
    ctx = context.gather(repo_path)
    QAAgent(settings, repo_path).run(
        f"Analyse test coverage for '{path}' and write or improve tests as needed.",
        extra_context=ctx,
    )


@app.command()
def plan(
    feature: Annotated[str, typer.Argument(help="Feature or task to plan.")],
    repo: RepoOption = Path("."),
) -> None:
    """Architect agent: plan an implementation before writing code."""
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    _banner("Architect", repo_path)
    ctx = context.gather(repo_path)
    ArchitectAgent(settings, repo_path).run(
        f"Plan the implementation of: {feature}",
        extra_context=ctx,
    )


@app.command()
def audit(
    path: Annotated[str, typer.Argument(help="File, directory, or 'staged' for staged changes.")] = ".",
    staged: Annotated[bool, typer.Option("--staged", help="Audit only staged changes.")] = False,
    repo: RepoOption = Path("."),
) -> None:
    """Security agent: OWASP checks, secrets detection, auth review."""
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    _banner("Security", repo_path)
    ctx = context.gather(repo_path)
    task = (
        "Audit the staged changes for security issues. Use get_git_diff with staged=true."
        if staged
        else f"Audit '{path}' for security issues."
    )
    SecurityAgent(settings, repo_path).run(task, extra_context=ctx)


# ---------------------------------------------------------------------------
# Pipeline command
# ---------------------------------------------------------------------------


@app.command()
def run(
    task: Annotated[str, typer.Argument(help="Full task description. Runs all agents in sequence.")],
    repo: RepoOption = Path("."),
    no_plan: Annotated[bool, typer.Option("--no-plan", help="Skip architecture planning step.")] = False,
    no_qa: Annotated[bool, typer.Option("--no-qa", help="Skip QA step.")] = False,
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Skip security audit step.")] = False,
    no_report: Annotated[bool, typer.Option("--no-report", help="Don't write briefing/brief.md.")] = False,
) -> None:
    """Full pipeline: architect → developer → reviewer → QA → security audit."""
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    console.print(Rule("[bold cyan]tech-team / Pipeline[/bold cyan]", style="cyan"))
    console.print(f"[dim]repo: {repo_path}[/dim]")
    console.print(f"[dim]task: {task}[/dim]\n")
    run_pipeline(
        task=task,
        settings=settings,
        repo_path=repo_path,
        skip_plan=no_plan,
        skip_qa=no_qa,
        skip_audit=no_audit,
        write_report=not no_report,
    )


# ---------------------------------------------------------------------------
# Check command — all analysis agents on recent changes or full repo
# ---------------------------------------------------------------------------


@app.command()
def check(
    repo: RepoOption = Path("."),
    full: Annotated[
        bool,
        typer.Option("--full", "-f", help="Check the entire repo, not just recent changes."),
    ] = False,
    base: Annotated[
        str,
        typer.Option("--base", "-b", help="Diff against this branch/commit instead of the remote tracking branch."),
    ] = "",
    no_review: Annotated[bool, typer.Option("--no-review", help="Skip code review.")] = False,
    no_qa: Annotated[bool, typer.Option("--no-qa", help="Skip QA / test coverage check.")] = False,
    no_arch: Annotated[bool, typer.Option("--no-arch", help="Skip architecture review.")] = False,
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Skip security audit.")] = False,
    report: Annotated[bool, typer.Option("--report", help="Write findings to briefing/brief.md.")] = False,
) -> None:
    """
    Run all analysis agents against recent unpushed changes (default) or the full repo (--full).

    \b
    Default scope — unpushed commits:
      Resolves to: git diff <tracking-branch>..HEAD
      Falls back to: git diff HEAD~1..HEAD if no tracking branch

    \b
    Flags:
      --full          Analyse the entire repo, not just the diff
      --base main     Diff against a specific branch or commit
      --no-review     Skip reviewer
      --no-qa         Skip QA
      --no-arch       Skip architect
      --no-audit      Skip security
      --report        Write briefing/brief.md

    \b
    Examples:
      tech-team check                   # review unpushed commits
      tech-team check --full            # review entire repo
      tech-team check --base main       # review everything not yet in main
      tech-team check --no-arch --no-qa # just review + security
    """
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    project_ctx = context.gather(repo_path)

    if full:
        scope = context.ChangeScope(
            full=True,
            diff="",
            changed_files=[],
            commits="",
            base_ref="",
            repo_path=repo_path,
        )
    else:
        scope = context.get_change_scope(repo_path, base=base)

    console.print(Rule("[bold cyan]tech-team / check[/bold cyan]", style="cyan"))
    console.print(f"[dim]repo:  {repo_path}[/dim]")
    console.print(f"[dim]scope: {scope.summary()}[/dim]")
    if not full and scope.changed_files:
        console.print(f"[dim]files: {', '.join(scope.changed_files[:6])}{'...' if len(scope.changed_files) > 6 else ''}[/dim]")
    console.print()

    scope_ctx = scope.as_prompt_context()
    extra = f"{project_ctx}\n\n{scope_ctx}" if project_ctx else scope_ctx

    findings: dict[str, str] = {}

    if not no_review:
        console.print(Rule("[cyan]Reviewer[/cyan]", style="dim"))
        task = (
            "Review the entire codebase for code quality, design patterns, regression risk, and accessibility."
            if full
            else "Review these changes for correctness, design patterns, regression risk, and accessibility. Focus only on what changed."
        )
        findings["review"] = ReviewerAgent(settings, repo_path).run(task, extra_context=extra)

    if not no_qa:
        console.print(Rule("[cyan]QA[/cyan]", style="dim"))
        task = (
            "Analyse test coverage across the entire codebase. Identify gaps and untested paths."
            if full
            else "Check whether these changes have adequate test coverage. Identify what's missing or insufficient."
        )
        findings["qa"] = QAAgent(settings, repo_path).run(task, extra_context=extra)

    if not no_arch:
        console.print(Rule("[cyan]Architect[/cyan]", style="dim"))
        task = (
            "Review the entire codebase for architectural consistency, design concerns, and technical debt."
            if full
            else "Review these changes for architectural concerns — missed abstractions, consistency issues, design problems."
        )
        findings["arch"] = ArchitectAgent(settings, repo_path).run(task, extra_context=extra)

    if not no_audit:
        console.print(Rule("[cyan]Security[/cyan]", style="dim"))
        task = (
            "Audit the entire codebase for security vulnerabilities, secrets, and auth gaps."
            if full
            else "Audit these changes for security issues — injection, secrets, auth, input validation."
        )
        findings["audit"] = SecurityAgent(settings, repo_path).run(task, extra_context=extra)

    if report:
        _write_check_report(repo_path, scope, findings)


def _write_check_report(repo_path: Path, scope: "context.ChangeScope", findings: dict[str, str]) -> None:
    labels = {"review": "Code review", "qa": "QA / test coverage", "arch": "Architecture", "audit": "Security audit"}
    sections = [f"# tech-team check report\n\n**Scope:** {scope.summary()}"]
    for key, output in findings.items():
        sections.append(f"## {labels.get(key, key)}\n\n{output}")
    report_path = repo_path / "briefing" / "brief.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
    console.print(f"\n[green]Brief written to {report_path}[/green]")


# ---------------------------------------------------------------------------
# Collaborative loop
# ---------------------------------------------------------------------------


@app.command()
def collab(
    task: Annotated[str, typer.Argument(help="What to implement.")],
    repo: RepoOption = Path("."),
    max_rounds: Annotated[int, typer.Option("--max-rounds", "-n", help="Maximum review/fix iterations.")] = 5,
    no_plan: Annotated[bool, typer.Option("--no-plan", help="Skip architect planning phase.")] = False,
    no_qa: Annotated[bool, typer.Option("--no-qa", help="Skip QA agent.")] = False,
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Skip security audit.")] = False,
    init: Annotated[bool, typer.Option("--init", help="git init the repo path if it has no .git directory.")] = False,
) -> None:
    """
    Collaborative loop: agents iterate until all satisfied, then you confirm.

    \b
    Flow:
      1. Architect plans  →  you approve the plan (no files written yet)
      2. Developer implements
      3. Reviewer + QA + Security analyse
      4. If issues found  →  Developer fixes  →  back to step 3
      5. Repeat up to --max-rounds
      6. Full diff shown  →  you confirm to keep or revert everything

    \b
    Architect triggers:
      Always runs at the start (step 1) unless --no-plan is passed.
      For a quick single-pass without the plan step: use  tech-team dev --plan
      For fire-and-forget with no confirmation:         use  tech-team run

    \b
    Examples:
      tech-team collab "add OAuth login"
      tech-team collab "refactor user service" --no-plan --max-rounds 3
      tech-team collab "add rate limiting" --no-audit
      tech-team collab "build a todo API" --repo ~/new-project --init
    """
    import subprocess as sp

    repo_path = _resolve_repo(repo)
    settings = _load_settings()

    if init and not (repo_path / ".git").exists():
        repo_path.mkdir(parents=True, exist_ok=True)
        sp.run(["git", "init"], cwd=repo_path, check=True)
        console.print(f"[green]Initialised git repo at {repo_path}[/green]\n")

    console.print(Rule("[bold cyan]tech-team / collab[/bold cyan]", style="cyan"))
    console.print(f"[dim]repo:  {repo_path}[/dim]")
    console.print(f"[dim]task:  {task}[/dim]")
    console.print(f"[dim]max rounds: {max_rounds}[/dim]\n")

    run_collab(
        task=task,
        settings=settings,
        repo_path=repo_path,
        max_rounds=max_rounds,
        skip_plan=no_plan,
        skip_qa=no_qa,
        skip_audit=no_audit,
    )


# ---------------------------------------------------------------------------
# Commit — generate a conventional commit message for staged changes
# ---------------------------------------------------------------------------

_COMMIT_SYSTEM_PROMPT = """\
Generate a conventional commit message for the given git diff.

Allowed prefixes: feat: fix: refactor: test: docs: chore: style: perf:
Rules:
- Imperative mood, lowercase, no trailing period, max 72 chars on the subject line
- Be specific: "add rate limiting to /api/chat" not "update api files"
- Add a blank line + short body only if the change genuinely needs more context
- No scope in parentheses unless it adds real clarity
- Output the commit message only — no explanation, no markdown, no code blocks
"""


@app.command()
def commit(
    repo: RepoOption = Path("."),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the generated message without committing.")] = False,
) -> None:
    """Generate a conventional commit message for staged changes and commit.

    \b
    Examples:
      git add src/auth.py tests/test_auth.py
      tech-team commit

      tech-team commit --dry-run   # preview message only
    """
    import subprocess as sp
    import anthropic as ant

    repo_path = _resolve_repo(repo)
    settings = _load_settings()

    diff = sp.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True, cwd=repo_path,
    ).stdout.strip()

    if not diff:
        console.print("[yellow]Nothing staged. Run git add first.[/yellow]")
        raise typer.Exit(1)

    _banner("Commit", repo_path)
    console.print("[dim]Generating message...[/dim]")

    if len(diff) > 8_000:
        diff = diff[:8_000] + "\n... (diff truncated)"

    client = ant.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.model,
        max_tokens=256,
        system=_COMMIT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"```diff\n{diff}\n```"}],
    )
    message = response.content[0].text.strip()  # type: ignore[union-attr]

    console.print()
    console.print(Rule("[cyan]Suggested message[/cyan]", style="dim"))
    console.print(f"\n  [bold green]{message}[/bold green]\n")

    if dry_run:
        return

    choice = typer.prompt("Use this message? [Y/n/e(dit)]", default="y").strip().lower()

    if choice == "n":
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit(0)
    if choice.startswith("e"):
        message = typer.prompt("Commit message")

    sp.run(["git", "commit", "-m", message], cwd=repo_path, check=True)
    console.print("[green]Done.[/green]")


# ---------------------------------------------------------------------------
# Fix — review staged changes and optionally auto-fix issues
# ---------------------------------------------------------------------------


@app.command()
def fix(
    repo: RepoOption = Path("."),
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Skip security audit.")] = False,
) -> None:
    """
    Review staged changes. If issues are found, offer to run the developer to fix them.

    \b
    This is the interactive companion to the pre-commit hook.

    \b
    Two ways to reach a clean commit:

      Path A — you wrote the code:
        git add <files>
        tech-team fix          ← reviews, fixes if needed, re-stages
        git commit

      Path B — agents write the code:
        tech-team collab "task"   ← implements, reviews, loops until clean
        git add <files>
        git commit

    \b
    The pre-commit hook runs the same review automatically on every commit.
    Use  tech-team fix  to resolve issues interactively before the hook fires.
    """
    import subprocess as sp

    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    ctx = context.gather(repo_path)

    _banner("Fix", repo_path)

    # Review staged changes
    console.print(Rule("[cyan]Reviewer — staged changes[/cyan]", style="dim"))
    review_out = ReviewerAgent(settings, repo_path).run(
        "Review staged changes only. Use get_git_diff with staged=true. "
        "Focus on correctness, regression risk, and accessibility.",
        extra_context=ctx,
    )

    audit_out = ""
    if not no_audit:
        console.print(Rule("[cyan]Security — staged changes[/cyan]", style="dim"))
        audit_out = SecurityAgent(settings, repo_path).run(
            "Audit staged changes only. Use get_git_diff with staged=true.",
            extra_context=ctx,
        )

    criticals, warnings = count_issues(review_out + audit_out)

    console.print()
    if criticals == 0 and warnings == 0:
        console.print("[bold green]No issues found. Ready to commit.[/bold green]")
        return

    summary_parts: list[str] = []
    if criticals:
        summary_parts.append(f"[red]{criticals} critical[/red]")
    if warnings:
        summary_parts.append(f"[yellow]{warnings} warning(s)[/yellow]")
    console.print(f"Found {', '.join(summary_parts)}.")
    console.print()

    if not typer.confirm("Run developer agent to fix these issues?", default=False):
        if criticals:
            console.print("[red]Commit blocked — critical issues must be resolved.[/red]")
            raise typer.Exit(1)
        console.print("[yellow]Warnings noted. Proceeding without fixes.[/yellow]")
        return

    # Developer fixes the issues found — working on top of the staged changes.
    # git checkout . only touches unstaged changes, so staged work is safe.
    console.print(Rule("[cyan]Developer — fixing issues[/cyan]", style="dim"))
    findings = f"## Code Review findings\n{review_out}"
    if audit_out:
        findings += f"\n\n## Security findings\n{audit_out}"

    DeveloperAgent(settings, repo_path).run(
        f"Fix the following issues found in the staged changes:\n\n{findings}",
        extra_context=ctx,
    )

    show_diff(repo_path, "Proposed fixes (unstaged on top of your staged changes)")

    if not typer.confirm("Apply fixes and re-stage?", default=True):
        sp.run(["git", "checkout", "."], cwd=repo_path, check=False)
        console.print("[dim]Fixes reverted. Your original staged changes are untouched.[/dim]")
        raise typer.Exit(1)

    sp.run(["git", "add", "-u"], cwd=repo_path, check=True)
    console.print("[green]Fixes applied and re-staged. Ready to commit.[/green]")


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------


@app.command()
def mcp() -> None:
    """Start the tech-team MCP server (stdio). Register with: tech-team install-mcp"""
    from src.mcp_server import mcp as server
    server.run()


@app.command("install-mcp")
def install_mcp(
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing entry.")] = False,
) -> None:
    """Register tech-team as an MCP server in Claude Code's global config (~/.claude.json)."""
    import json
    import shutil

    tech_team_bin = shutil.which("tech-team")
    if not tech_team_bin:
        console.print("[red]tech-team not found on PATH. Run: pip install -e .[/red]")
        raise typer.Exit(1)

    config_path = Path.home() / ".claude.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            config = {}

    config.setdefault("mcpServers", {})

    if "tech-team" in config["mcpServers"] and not force:
        console.print("[yellow]tech-team already in ~/.claude.json[/yellow]")
        console.print("[dim]Use --force to overwrite.[/dim]")
        raise typer.Exit(0)

    config["mcpServers"]["tech-team"] = {
        "type": "stdio",
        "command": tech_team_bin,
        "args": ["mcp"],
    }

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"[green]Registered tech-team MCP server in {config_path}[/green]")
    console.print("[dim]Restart Claude Code to pick up the new MCP server.[/dim]")
    console.print()
    console.print("Available tools in Claude Code:")
    for tool in ("developer", "reviewer", "qa_engineer", "architect", "security", "check"):
        console.print(f"  [cyan]{tool}[/cyan]")


# ---------------------------------------------------------------------------
# Pre-commit hook mode
# ---------------------------------------------------------------------------


@app.command("pre-commit")
def pre_commit(
    repo: RepoOption = Path("."),
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Skip security audit.")] = False,
) -> None:
    """
    Pre-commit hook mode: review and audit staged changes.
    Exits 1 if CRITICAL issues are found.
    """
    repo_path = _resolve_repo(repo)
    settings = _load_settings()
    ctx = context.gather(repo_path)

    console.print(Rule("[bold cyan]tech-team / pre-commit[/bold cyan]", style="cyan"))
    console.print(f"[dim]repo: {repo_path}[/dim]\n")

    task_review = (
        "Review the staged changes. Use get_git_diff with staged=true. "
        "Focus on correctness, regression risk, and critical issues."
    )
    task_audit = (
        "Audit the staged changes for security issues. Use get_git_diff with staged=true."
    )

    console.print(Rule("[cyan]Reviewer[/cyan]", style="dim"))
    review_output = ReviewerAgent(settings, repo_path).run(task_review, extra_context=ctx)

    audit_output = ""
    if not no_audit:
        console.print(Rule("[cyan]Security[/cyan]", style="dim"))
        audit_output = SecurityAgent(settings, repo_path).run(task_audit, extra_context=ctx)

    # Exit 1 if any CRITICAL findings
    combined = (review_output + "\n" + audit_output).upper()
    if "[CRITICAL]" in combined:
        console.print("\n[bold red]CRITICAL issues found — commit blocked.[/bold red]")
        console.print("[dim]Fix the issues above and try again, or use git commit --no-verify to bypass.[/dim]")
        raise typer.Exit(1)

    console.print("\n[green]No critical issues. Proceeding with commit.[/green]")


# ---------------------------------------------------------------------------
# Hook installation
# ---------------------------------------------------------------------------


@app.command("install-hook")
def install_hook(
    repo: RepoOption = Path("."),
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Disable security audit in hook.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing hook.")] = False,
) -> None:
    """Install tech-team as a pre-commit hook in the target repo."""
    repo_path = _resolve_repo(repo)
    hooks_dir = repo_path / ".git" / "hooks"

    if not hooks_dir.exists():
        console.print(f"[red]No .git/hooks directory found at {repo_path}[/red]")
        console.print("[dim]Make sure this is a git repository.[/dim]")
        raise typer.Exit(1)

    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists() and not force:
        console.print(f"[yellow]Hook already exists at {hook_path}[/yellow]")
        console.print("[dim]Use --force to overwrite.[/dim]")
        raise typer.Exit(1)

    audit_flag = " --no-audit" if no_audit else ""
    hook_content = f"""\
#!/usr/bin/env bash
# Installed by tech-team. Remove this file to disable.
set -e
tech-team pre-commit{audit_flag} --repo "$(git rev-parse --show-toplevel)"
"""
    hook_path.write_text(hook_content, encoding="utf-8")
    hook_path.chmod(0o755)
    console.print(f"[green]Hook installed at {hook_path}[/green]")
    console.print("[dim]tech-team will run on every commit. Uninstall: rm .git/hooks/pre-commit[/dim]")


# ---------------------------------------------------------------------------
# Global hook installation (applies to every repo on this machine)
# ---------------------------------------------------------------------------


@app.command("install-global-hook")
def install_global_hook(
    hooks_dir: Annotated[
        Path,
        typer.Option("--hooks-dir", help="Directory to store global hooks."),
    ] = Path.home() / ".config" / "git" / "hooks",
    no_audit: Annotated[bool, typer.Option("--no-audit", help="Disable security audit in hook.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing hook.")] = False,
) -> None:
    """
    Install tech-team as a global pre-commit hook for every git repo on this machine.

    Uses git's core.hooksPath to point all repos at a shared hooks directory.
    Bypass on any commit with: git commit --no-verify
    Remove with: tech-team remove-global-hook
    """
    import shutil
    import subprocess

    # Find the tech-team executable so the hook uses the full path —
    # the venv won't be active when git triggers the hook.
    tech_team_bin = shutil.which("tech-team")
    if tech_team_bin is None:
        console.print("[red]tech-team not found on PATH.[/red]")
        console.print("[dim]Run: pip install -e . from the tech-team-ai directory first.[/dim]")
        raise typer.Exit(1)

    hooks_dir = hooks_dir.resolve()
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists() and not force:
        console.print(f"[yellow]Global hook already exists at {hook_path}[/yellow]")
        console.print("[dim]Use --force to overwrite.[/dim]")
        raise typer.Exit(1)

    audit_flag = " --no-audit" if no_audit else ""
    hook_content = f"""\
#!/usr/bin/env bash
# Global pre-commit hook managed by tech-team.
# Bypass: git commit --no-verify
# Remove: tech-team remove-global-hook

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Skip if the repo has opted out via .no-tech-team file
if [ -f "$REPO_ROOT/.no-tech-team" ]; then
  exit 0
fi

"{tech_team_bin}" pre-commit{audit_flag} --repo "$REPO_ROOT"
"""

    hook_path.write_text(hook_content, encoding="utf-8")
    hook_path.chmod(0o755)

    # Point git at the global hooks directory
    subprocess.run(
        ["git", "config", "--global", "core.hooksPath", str(hooks_dir)],
        check=True,
    )

    console.print(f"[green]Global hook installed at {hook_path}[/green]")
    console.print(f"[green]git config --global core.hooksPath = {hooks_dir}[/green]")
    console.print()
    console.print("[dim]tech-team will now run on every git commit on this machine.[/dim]")
    console.print("[dim]Bypass a single commit: git commit --no-verify[/dim]")
    console.print("[dim]Opt a repo out: touch <repo>/.no-tech-team[/dim]")
    console.print("[dim]Remove entirely: tech-team remove-global-hook[/dim]")


@app.command("remove-global-hook")
def remove_global_hook() -> None:
    """Remove the global pre-commit hook and unset core.hooksPath."""
    import subprocess

    result = subprocess.run(
        ["git", "config", "--global", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    hooks_dir_str = result.stdout.strip()

    if not hooks_dir_str:
        console.print("[yellow]No global core.hooksPath is set — nothing to remove.[/yellow]")
        raise typer.Exit(0)

    hook_path = Path(hooks_dir_str) / "pre-commit"
    if hook_path.exists():
        hook_path.unlink()
        console.print(f"[green]Removed {hook_path}[/green]")
    else:
        console.print(f"[dim]No pre-commit hook found at {hook_path}[/dim]")

    subprocess.run(
        ["git", "config", "--global", "--unset", "core.hooksPath"],
        check=True,
    )
    console.print("[green]Unset git config --global core.hooksPath[/green]")
    console.print("[dim]Global hook removed. Per-repo hooks in .git/hooks/ will work as normal.[/dim]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
