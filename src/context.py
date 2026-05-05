"""Gather project context to inject into agent prompts so they don't start cold."""

import subprocess
from pathlib import Path


_STACK_MARKERS = {
    "pyproject.toml": "Python (pyproject.toml)",
    "setup.py": "Python (setup.py)",
    "requirements.txt": "Python (requirements.txt)",
    "package.json": "Node.js / JavaScript / TypeScript",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
}


def gather(repo_path: Path, max_readme_chars: int = 3000) -> str:
    """
    Build a project context string to prepend to agent tasks.
    Keeps it short — just enough for the agent to orient itself.
    """
    sections: list[str] = []

    # Project instructions (CLAUDE.md takes priority, then README)
    for filename in ("CLAUDE.md", "README.md"):
        doc = repo_path / filename
        if doc.exists():
            content = doc.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_readme_chars:
                content = content[:max_readme_chars] + "\n... (truncated)"
            sections.append(f"## {filename}\n{content}")
            break

    # Tech stack detection
    detected = [label for marker, label in _STACK_MARKERS.items() if (repo_path / marker).exists()]
    if detected:
        sections.append(f"## Tech stack\n" + "\n".join(f"- {s}" for s in detected))

    # Top-level directory structure
    try:
        entries = sorted(repo_path.iterdir(), key=lambda p: (p.is_file(), p.name))
        tree_lines = []
        for entry in entries[:40]:
            if entry.name.startswith(".") and entry.name not in (".github",):
                continue
            suffix = "/" if entry.is_dir() else ""
            tree_lines.append(f"  {entry.name}{suffix}")
        if tree_lines:
            sections.append("## Project structure (top level)\n" + "\n".join(tree_lines))
    except OSError:
        pass

    # Current git branch and recent commits
    branch = _git(repo_path, ["git", "branch", "--show-current"])
    log = _git(repo_path, ["git", "log", "--oneline", "-5"])
    if branch or log:
        git_info = []
        if branch:
            git_info.append(f"Branch: {branch}")
        if log:
            git_info.append(f"Recent commits:\n{log}")
        sections.append("## Git context\n" + "\n".join(git_info))

    if not sections:
        return ""

    header = f"# Project context\nRepo path: {repo_path}\n"
    return header + "\n\n".join(sections)


class ChangeScope:
    """Describes what changed — either a targeted diff or the whole repo."""

    def __init__(
        self,
        *,
        full: bool,
        diff: str,
        changed_files: list[str],
        commits: str,
        base_ref: str,
        repo_path: Path,
    ) -> None:
        self.full = full
        self.diff = diff
        self.changed_files = changed_files
        self.commits = commits
        self.base_ref = base_ref
        self.repo_path = repo_path

    def summary(self) -> str:
        """Short human-readable description of the scope, for terminal output."""
        if self.full:
            return "entire repo"
        if self.base_ref:
            return f"changes vs {self.base_ref}"
        return "unpushed commits"

    def as_prompt_context(self) -> str:
        """Inject into an agent task so it knows exactly what to focus on."""
        if self.full:
            return (
                "## Scope\nFull repository scan. Analyse all files — not limited to recent changes."
            )

        parts = ["## Scope\nFocused on recent changes only (not the full repo)."]

        if self.base_ref:
            parts.append(f"Base ref: `{self.base_ref}`")

        if self.commits:
            parts.append(f"### Commits in scope\n```\n{self.commits}\n```")

        if self.changed_files:
            file_list = "\n".join(f"  - {f}" for f in self.changed_files)
            parts.append(f"### Changed files\n{file_list}")

        if self.diff:
            diff_preview = self.diff
            if len(diff_preview) > 12_000:
                diff_preview = diff_preview[:12_000] + "\n... (diff truncated — read full files for detail)"
            parts.append(f"### Diff\n```diff\n{diff_preview}\n```")
        else:
            parts.append("No diff available — the repo may be clean or have no remote tracking branch.")

        return "\n\n".join(parts)


def get_change_scope(repo_path: Path, base: str = "") -> ChangeScope:
    """
    Determine what's changed and return a ChangeScope.

    Resolution order when no base is specified:
    1. Commits not yet pushed to the tracking remote branch
    2. Last commit (HEAD~1..HEAD) if no tracking branch exists
    3. Staged changes if nothing else is found
    """
    # Explicit base ref supplied via --base flag
    if base:
        diff = _git(repo_path, ["git", "diff", f"{base}...HEAD"])
        commits = _git(repo_path, ["git", "log", "--oneline", f"{base}...HEAD"])
        files = _changed_files(repo_path, f"{base}...HEAD")
        return ChangeScope(
            full=False,
            diff=diff,
            changed_files=files,
            commits=commits,
            base_ref=base,
            repo_path=repo_path,
        )

    # Try upstream tracking branch (unpushed commits)
    tracking = _git(repo_path, ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if tracking:
        diff = _git(repo_path, ["git", "diff", f"{tracking}..HEAD"])
        commits = _git(repo_path, ["git", "log", "--oneline", f"{tracking}..HEAD"])
        files = _changed_files(repo_path, f"{tracking}..HEAD")
        # If nothing unpushed yet, fall through to last-commit logic
        if commits or diff:
            return ChangeScope(
                full=False,
                diff=diff,
                changed_files=files,
                commits=commits,
                base_ref=tracking,
                repo_path=repo_path,
            )

    # Fallback: last commit
    diff = _git(repo_path, ["git", "diff", "HEAD~1..HEAD"])
    commits = _git(repo_path, ["git", "log", "--oneline", "-1"])
    files = _changed_files(repo_path, "HEAD~1..HEAD")
    return ChangeScope(
        full=False,
        diff=diff,
        changed_files=files,
        commits=commits,
        base_ref="HEAD~1",
        repo_path=repo_path,
    )


def _changed_files(repo_path: Path, ref_range: str) -> list[str]:
    out = _git(repo_path, ["git", "diff", "--name-only", ref_range])
    return [f for f in out.splitlines() if f]


def _git(repo_path: Path, cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""
