"""Tests for agent infrastructure — no real API calls."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import Settings
from src.tools.executor import ToolExecutor


# ---------------------------------------------------------------------------
# ToolExecutor tests
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def hello():\n    return 'hello'\n")
    (tmp_path / "README.md").write_text("# Test project\n")
    return tmp_path


@pytest.fixture
def executor(repo: Path) -> ToolExecutor:
    return ToolExecutor(repo_path=repo, allow_writes=True, timeout=10)


@pytest.fixture
def readonly_executor(repo: Path) -> ToolExecutor:
    return ToolExecutor(repo_path=repo, allow_writes=False, timeout=10)


class TestReadFile:
    def test_reads_existing_file(self, executor: ToolExecutor) -> None:
        result = executor.execute("read_file", {"path": "src/main.py"})
        assert "def hello" in result

    def test_returns_error_for_missing_file(self, executor: ToolExecutor) -> None:
        result = executor.execute("read_file", {"path": "nonexistent.py"})
        assert "Error" in result

    def test_blocks_path_traversal(self, executor: ToolExecutor) -> None:
        result = executor.execute("read_file", {"path": "../../etc/passwd"})
        assert "Error" in result
        assert "outside the project root" in result


class TestListDirectory:
    def test_lists_files(self, executor: ToolExecutor) -> None:
        result = executor.execute("list_directory", {"path": "."})
        assert "src" in result
        assert "README.md" in result

    def test_returns_error_for_missing_dir(self, executor: ToolExecutor) -> None:
        result = executor.execute("list_directory", {"path": "nonexistent"})
        assert "Error" in result


class TestWriteFile:
    def test_creates_new_file(self, executor: ToolExecutor, repo: Path) -> None:
        result = executor.execute("write_file", {"path": "new_file.py", "content": "x = 1\n"})
        assert "Written" in result
        assert (repo / "new_file.py").read_text() == "x = 1\n"

    def test_creates_nested_directories(self, executor: ToolExecutor, repo: Path) -> None:
        executor.execute("write_file", {"path": "a/b/c.py", "content": "pass\n"})
        assert (repo / "a" / "b" / "c.py").exists()

    def test_blocked_when_readonly(self, readonly_executor: ToolExecutor) -> None:
        result = readonly_executor.execute("write_file", {"path": "x.py", "content": "x"})
        assert "Error" in result
        assert "write permissions" in result


class TestPatchFile:
    def test_replaces_exact_string(self, executor: ToolExecutor, repo: Path) -> None:
        result = executor.execute(
            "patch_file",
            {"path": "src/main.py", "old_string": "return 'hello'", "new_string": "return 'world'"},
        )
        assert "Patched" in result
        assert "return 'world'" in (repo / "src" / "main.py").read_text()

    def test_errors_when_string_not_found(self, executor: ToolExecutor) -> None:
        result = executor.execute(
            "patch_file",
            {"path": "src/main.py", "old_string": "does not exist", "new_string": "replacement"},
        )
        assert "Error" in result
        assert "not found" in result

    def test_errors_when_string_not_unique(self, executor: ToolExecutor, repo: Path) -> None:
        (repo / "dup.py").write_text("x = 1\nx = 1\n")
        result = executor.execute(
            "patch_file",
            {"path": "dup.py", "old_string": "x = 1", "new_string": "x = 2"},
        )
        assert "Error" in result
        assert "times" in result


class TestRunShell:
    def test_runs_safe_command(self, executor: ToolExecutor) -> None:
        result = executor.execute("run_shell", {"command": "echo hello"})
        assert "hello" in result

    def test_blocks_rm_rf(self, executor: ToolExecutor) -> None:
        result = executor.execute("run_shell", {"command": "rm -rf /"})
        assert "Blocked" in result

    def test_blocks_git_push(self, executor: ToolExecutor) -> None:
        result = executor.execute("run_shell", {"command": "git push origin main"})
        assert "Blocked" in result

    def test_blocks_sudo(self, executor: ToolExecutor) -> None:
        result = executor.execute("run_shell", {"command": "sudo apt install something"})
        assert "Blocked" in result

    def test_blocks_git_reset_hard(self, executor: ToolExecutor) -> None:
        result = executor.execute("run_shell", {"command": "git reset --hard HEAD~1"})
        assert "Blocked" in result


class TestUnknownTool:
    def test_returns_error_for_unknown_tool(self, executor: ToolExecutor) -> None:
        result = executor.execute("does_not_exist", {})
        assert "Unknown tool" in result


# ---------------------------------------------------------------------------
# Agent base — mock the Anthropic client
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        anthropic_api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=1024,
        shell_timeout=10,
    )


def _mock_text_response(text: str) -> MagicMock:
    """Build a mock Anthropic response that returns text and no tool calls."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    return response


class TestBaseAgentLoop:
    def test_returns_text_on_end_turn(self, settings: Settings, repo: Path) -> None:
        from src.agents.developer import DeveloperAgent

        agent = DeveloperAgent(settings, repo)

        with patch.object(agent.client.messages, "create", return_value=_mock_text_response("Done!")):
            result = agent.run("do something", stream=False)

        assert result == "Done!"

    def test_executes_tool_and_continues(self, settings: Settings, repo: Path) -> None:
        from src.agents.developer import DeveloperAgent

        agent = DeveloperAgent(settings, repo)

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_1"
        tool_block.name = "list_directory"
        tool_block.input = {"path": "."}

        tool_response = MagicMock()
        tool_response.content = [tool_block]
        tool_response.stop_reason = "tool_use"

        final_response = _mock_text_response("Listed the directory.")

        responses = iter([tool_response, final_response])

        with patch.object(agent.client.messages, "create", side_effect=lambda **_: next(responses)):
            result = agent.run("list directory", stream=False)

        assert result == "Listed the directory."
