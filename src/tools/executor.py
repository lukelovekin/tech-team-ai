"""Tool execution — dispatches tool calls from agents to actual file/shell operations."""

import subprocess
from pathlib import Path


# Commands that are never allowed, regardless of context.
_BLOCKED_PATTERNS = [
    "rm -rf",
    "git push",
    "git reset --hard",
    "git checkout --",
    "git clean -f",
    "git clean -fd",
    "sudo",
    "chmod -R 777",
    "chmod 777",
    "dd if=",
    "mkfs",
    "> /dev/",
    ":(){ :|:& };:",
    "curl | sh",
    "curl | bash",
    "wget | sh",
    "wget | bash",
]


class ToolExecutor:
    def __init__(self, repo_path: Path, allow_writes: bool = False, timeout: int = 120) -> None:
        self.repo_path = repo_path.resolve()
        self.allow_writes = allow_writes
        self.timeout = timeout

    def execute(self, tool_name: str, tool_input: dict) -> str:  # type: ignore[type-arg]
        match tool_name:
            case "read_file":
                return self._read_file(**tool_input)
            case "list_directory":
                return self._list_directory(**tool_input)
            case "search_code":
                return self._search_code(**tool_input)
            case "get_git_diff":
                return self._get_git_diff(**tool_input)
            case "get_git_log":
                return self._get_git_log(**tool_input)
            case "run_shell":
                return self._run_shell(**tool_input)
            case "write_file":
                return self._write_file(**tool_input)
            case "patch_file":
                return self._patch_file(**tool_input)
            case _:
                return f"Unknown tool: {tool_name}"

    # --- read-only tools ---

    def _read_file(self, path: str) -> str:
        target = self._safe_path(path)
        if target is None:
            return f"Error: {path} is outside the project root"
        if not target.exists():
            return f"Error: {path} does not exist"
        if not target.is_file():
            return f"Error: {path} is a directory, not a file"
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading {path}: {e}"

    def _list_directory(self, path: str = ".") -> str:
        target = self._safe_path(path)
        if target is None:
            return f"Error: {path} is outside the project root"
        if not target.exists():
            return f"Error: {path} does not exist"
        if not target.is_dir():
            return f"Error: {path} is not a directory"

        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            prefix = "" if entry.is_file() else "/"
            lines.append(f"{entry.name}{prefix}")
        return "\n".join(lines) if lines else "(empty directory)"

    def _search_code(self, pattern: str, path: str = ".", file_glob: str = "") -> str:
        search_path = self._safe_path(path) or self.repo_path
        cmd = ["grep", "-rn", "--include", file_glob or "*", pattern, str(search_path)]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if not output:
            return f"No matches for '{pattern}'"
        # Trim very long results
        lines = output.splitlines()
        if len(lines) > 200:
            return "\n".join(lines[:200]) + f"\n... ({len(lines) - 200} more lines truncated)"
        return output

    def _get_git_diff(self, staged: bool = False, path: str = "") -> str:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")
        if path:
            cmd += ["--", path]
        return self._run_git(cmd)

    def _get_git_log(self, n: int = 10, path: str = "") -> str:
        cmd = ["git", "log", f"-{n}", "--oneline", "--decorate"]
        if path:
            cmd += ["--", path]
        return self._run_git(cmd)

    def _run_shell(self, command: str) -> str:
        blocked = self._check_blocked(command)
        if blocked:
            return f"Blocked: '{blocked}' is not permitted. This guard prevents destructive operations."
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=self.timeout,
            )
            output = result.stdout + result.stderr
            if len(output) > 10_000:
                output = output[:10_000] + "\n... (output truncated)"
            return output.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {self.timeout}s"
        except OSError as e:
            return f"Error: {e}"

    # --- write tools ---

    def _write_file(self, path: str, content: str) -> str:
        if not self.allow_writes:
            return "Error: this agent does not have write permissions"
        target = self._safe_path(path)
        if target is None:
            return f"Error: {path} is outside the project root"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written: {path}"

    def _patch_file(self, path: str, old_string: str, new_string: str) -> str:
        if not self.allow_writes:
            return "Error: this agent does not have write permissions"
        target = self._safe_path(path)
        if target is None:
            return f"Error: {path} is outside the project root"
        if not target.exists():
            return f"Error: {path} does not exist"

        content = target.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return f"Error: old_string not found in {path}"
        if count > 1:
            return f"Error: old_string found {count} times in {path} — provide more context to make it unique"

        target.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
        return f"Patched: {path}"

    # --- helpers ---

    def _safe_path(self, path: str) -> Path | None:
        """Resolve path and ensure it stays within repo_path."""
        resolved = (self.repo_path / path).resolve()
        if not str(resolved).startswith(str(self.repo_path)):
            return None
        return resolved

    def _run_git(self, cmd: list[str]) -> str:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.repo_path),
                timeout=30,
            )
            return (result.stdout + result.stderr).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: git command timed out"
        except OSError as e:
            return f"Error: {e}"

    @staticmethod
    def _check_blocked(command: str) -> str | None:
        lower = command.lower()
        for pattern in _BLOCKED_PATTERNS:
            if pattern in lower:
                return pattern
        return None
