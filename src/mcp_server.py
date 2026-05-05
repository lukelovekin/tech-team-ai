"""
FastMCP server — exposes all tech-team agents as MCP tools.

Claude Code (and any MCP client) can call these tools mid-conversation:
  - developer    implement a feature or fix
  - reviewer     review code for quality, patterns, accessibility, regression
  - qa_engineer  check/improve test coverage
  - architect    plan before coding
  - security     OWASP / secrets / auth audit
  - check        run all analysis agents on recent changes or the full repo

Start the server:
  tech-team mcp

Register with Claude Code:
  tech-team install-mcp
"""

import os
from pathlib import Path

from fastmcp import FastMCP

from src import context as ctx_module
from src.agents.architect import ArchitectAgent
from src.agents.developer import DeveloperAgent
from src.agents.qa import QAAgent
from src.agents.reviewer import ReviewerAgent
from src.agents.security import SecurityAgent
from src.config import Settings, find_repo_root

mcp = FastMCP(
    "tech-team",
    instructions=(
        "AI software team. Each tool runs a specialist Claude agent on the target repository. "
        "Pass repo_path as the absolute path to the project root. "
        "If omitted, the nearest git root from the current working directory is used."
    ),
)


def _repo(repo_path: str) -> Path:
    if repo_path:
        return Path(repo_path).resolve()
    return find_repo_root(Path(os.getcwd()))


def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Individual agent tools
# ---------------------------------------------------------------------------


@mcp.tool()
def developer(task: str, repo_path: str = "") -> str:
    """
    Developer agent: implement a feature or bug fix from a task description.

    Reads existing code patterns and conventions before writing anything,
    then produces code that matches the project style. Can create and modify files.

    Args:
        task: What to implement. Can be a prompt, ticket description, or acceptance criteria.
        repo_path: Absolute path to the project root. Defaults to nearest git root.
    """
    settings = _settings()
    repo = _repo(repo_path)
    extra = ctx_module.gather(repo)
    return DeveloperAgent(settings, repo).run(task, extra_context=extra, stream=False)


@mcp.tool()
def reviewer(
    task: str,
    repo_path: str = "",
    staged_only: bool = False,
) -> str:
    """
    Reviewer agent: review code for quality, design patterns, accessibility, and regression risk.

    Produces structured findings with severity labels (CRITICAL / WARNING / INFO)
    and ends with an overall verdict (approve / request changes).

    Args:
        task: What to review — a file path, description of changes, or 'review staged changes'.
        repo_path: Absolute path to the project root. Defaults to nearest git root.
        staged_only: If True, review only staged (pre-commit) changes.
    """
    settings = _settings()
    repo = _repo(repo_path)
    extra = ctx_module.gather(repo)
    if staged_only:
        task = f"Review staged changes only. Use get_git_diff with staged=true. {task}"
    return ReviewerAgent(settings, repo).run(task, extra_context=extra, stream=False)


@mcp.tool()
def qa_engineer(task: str, repo_path: str = "") -> str:
    """
    QA agent: analyse test coverage and write or improve tests.

    Reads existing test patterns, identifies gaps, and writes tests that cover
    edge cases and failure paths — not just happy paths.

    Args:
        task: What to test — a file, module, or description of recent changes.
        repo_path: Absolute path to the project root. Defaults to nearest git root.
    """
    settings = _settings()
    repo = _repo(repo_path)
    extra = ctx_module.gather(repo)
    return QAAgent(settings, repo).run(task, extra_context=extra, stream=False)


@mcp.tool()
def architect(task: str, repo_path: str = "") -> str:
    """
    Architect agent: plan an implementation before any code is written.

    Returns a structured plan: files to change/create, implementation steps,
    risks, and open questions. Writes ADRs for significant decisions.

    Use this before calling developer() on anything non-trivial.

    Args:
        task: Feature or change to plan.
        repo_path: Absolute path to the project root. Defaults to nearest git root.
    """
    settings = _settings()
    repo = _repo(repo_path)
    extra = ctx_module.gather(repo)
    return ArchitectAgent(settings, repo).run(
        f"Plan the implementation of: {task}", extra_context=extra, stream=False
    )


@mcp.tool()
def security(task: str, repo_path: str = "") -> str:
    """
    Security agent: audit code for OWASP vulnerabilities, hardcoded secrets, and auth gaps.

    Checks for: injection, XSS, missing auth, weak crypto, secrets in code,
    insecure shell usage, and path traversal. Outputs findings with severity labels.

    Args:
        task: What to audit — a file, module, or 'audit staged changes'.
        repo_path: Absolute path to the project root. Defaults to nearest git root.
    """
    settings = _settings()
    repo = _repo(repo_path)
    extra = ctx_module.gather(repo)
    return SecurityAgent(settings, repo).run(task, extra_context=extra, stream=False)


# ---------------------------------------------------------------------------
# Multi-agent tools
# ---------------------------------------------------------------------------


@mcp.tool()
def check(
    repo_path: str = "",
    full_repo: bool = False,
    base: str = "",
    skip_qa: bool = False,
    skip_arch: bool = False,
    skip_audit: bool = False,
) -> str:
    """
    Run all analysis agents against recent unpushed changes (default) or the full repo.

    Combines: reviewer + QA + architect + security into one structured report.

    Args:
        repo_path: Absolute path to the project root. Defaults to nearest git root.
        full_repo: If True, analyse the entire codebase instead of just recent changes.
        base: Diff against this branch/commit (e.g. 'main') instead of the remote tracking branch.
        skip_qa: Skip QA agent.
        skip_arch: Skip architect agent.
        skip_audit: Skip security agent.
    """
    settings = _settings()
    repo = _repo(repo_path)
    project_ctx = ctx_module.gather(repo)

    if full_repo:
        scope = ctx_module.ChangeScope(
            full=True, diff="", changed_files=[], commits="", base_ref="", repo_path=repo
        )
    else:
        scope = ctx_module.get_change_scope(repo, base=base)

    extra = f"{project_ctx}\n\n{scope.as_prompt_context()}"

    agents: list[tuple[type, str, str]] = [
        (ReviewerAgent, "Code Review", "Review for quality, patterns, regression risk, and accessibility."),
    ]
    if not skip_qa:
        agents.append((QAAgent, "QA", "Check test coverage for these changes."))
    if not skip_arch:
        agents.append((ArchitectAgent, "Architecture", "Review for architectural concerns and consistency."))
    if not skip_audit:
        agents.append((SecurityAgent, "Security", "Audit for vulnerabilities, secrets, and auth gaps."))

    sections = [f"# tech-team check\nScope: {scope.summary()}\n"]
    for agent_cls, label, task in agents:
        output = agent_cls(settings, repo).run(task, extra_context=extra, stream=False)
        sections.append(f"## {label}\n\n{output}")

    return "\n\n---\n\n".join(sections)
