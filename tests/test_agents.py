"""Tests for agent infrastructure — no real API calls."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import httpx
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


class TestBadArguments:
    def test_wrong_args_return_error_not_crash(self, executor: ToolExecutor) -> None:
        # Model sends write_file without the required 'content' argument.
        result = executor.execute("write_file", {"path": "x.py"})
        assert "Error" in result
        assert "write_file" in result

    def test_wrong_arg_name_returns_error(self, executor: ToolExecutor) -> None:
        # Model sends 'contents' instead of 'content'.
        result = executor.execute("write_file", {"path": "x.py", "contents": "hello"})
        assert "Error" in result


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

    def test_retries_on_dropped_connection(self, settings: Settings, repo: Path) -> None:
        from src.agents.developer import DeveloperAgent

        agent = DeveloperAgent(settings, repo)
        good_response = _mock_text_response("Done after retry.")

        call_count = 0

        def flaky(**_):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.RemoteProtocolError("peer closed connection", request=MagicMock())
            return good_response

        with patch.object(agent.client.messages, "create", side_effect=flaky):
            result = agent.run("do something", stream=False)

        assert result == "Done after retry."
        assert call_count == 2

    def test_raises_after_max_retries(self, settings: Settings, repo: Path) -> None:
        from src.agents.developer import DeveloperAgent

        agent = DeveloperAgent(settings, repo)

        def always_drops(**_):  # type: ignore[no-untyped-def]
            raise httpx.RemoteProtocolError("peer closed connection", request=MagicMock())

        with patch.object(agent.client.messages, "create", side_effect=always_drops):
            with pytest.raises(httpx.RemoteProtocolError):
                agent.run("do something", stream=False)

# ---------------------------------------------------------------------------
# Collab helpers
# ---------------------------------------------------------------------------


class TestContextGather:
    def test_includes_architect_briefing_when_present(self, repo: Path) -> None:
        from src.context import gather

        (repo / "briefing").mkdir()
        (repo / "briefing" / "context.md").write_text("## Key files\nmain.py: entry point\n")

        result = gather(repo)
        assert "Architect's codebase briefing" in result
        assert "Key files" in result

    def test_skips_entry_points_when_briefing_present(self, repo: Path) -> None:
        from src.context import gather

        (repo / "briefing").mkdir()
        (repo / "briefing" / "context.md").write_text("briefing content")
        (repo / "main.py").write_text("# entry point")

        result = gather(repo)
        assert "Entry points" not in result

    def test_reads_entry_points_when_no_briefing(self, repo: Path) -> None:
        from src.context import gather

        (repo / "main.py").write_text("def main(): pass\n")

        result = gather(repo)
        assert "Entry points" in result
        assert "def main" in result

    def test_no_briefing_no_entry_points_still_works(self, repo: Path) -> None:
        from src.context import gather

        result = gather(repo)
        assert "Project context" in result


class TestWriteBrief:
    def test_writes_brief_file(self, repo: Path) -> None:
        from src.collab import _write_brief

        _write_brief(repo, "build a todo app", "the plan", "review findings", "qa findings", "audit findings")

        brief = (repo / "briefing" / "brief.md").read_text()
        assert "build a todo app" in brief
        assert "the plan" in brief
        assert "review findings" in brief
        assert "qa findings" in brief
        assert "audit findings" in brief

    def test_omits_empty_sections(self, repo: Path) -> None:
        from src.collab import _write_brief

        _write_brief(repo, "build a todo app", "", "review findings", "", "")

        brief = (repo / "briefing" / "brief.md").read_text()
        assert "Architecture plan" not in brief
        assert "QA" not in brief
        assert "Security" not in brief
        assert "review findings" in brief

    def test_creates_briefing_directory(self, tmp_path: Path) -> None:
        from src.collab import _write_brief

        assert not (tmp_path / "briefing").exists()
        _write_brief(tmp_path, "task", "plan", "", "", "")
        assert (tmp_path / "briefing" / "brief.md").exists()


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
