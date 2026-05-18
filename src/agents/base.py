"""BaseAgent: agentic tool-use loop with streaming and prompt caching."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import time

import anthropic
import httpx
from rich.console import Console
from rich.markup import escape

from src.config import Settings
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolDefinition

console = Console()


class BaseAgent(ABC):
    SYSTEM_PROMPT: str = ""
    TOOLS: list[ToolDefinition] = []
    ALLOW_WRITES: bool = False

    def __init__(self, settings: Settings, repo_path: Path) -> None:
        self.settings = settings
        self.repo_path = repo_path
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.executor = ToolExecutor(
            repo_path=repo_path,
            allow_writes=self.ALLOW_WRITES,
            timeout=settings.shell_timeout,
        )

    @property
    @abstractmethod
    def name(self) -> str: ...

    def run(self, task: str, extra_context: str = "", stream: bool = True) -> str:
        """
        Run the agent on a task. Returns the final text response.
        Streams output to the terminal unless stream=False.
        """
        user_content = task
        if extra_context:
            user_content = f"{extra_context}\n\n---\n\n{task}"

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        final_text = ""

        while True:
            response_text, stop_reason, tool_calls = self._call(messages, stream=stream)
            final_text = response_text

            if stop_reason == "end_turn" or not tool_calls:
                break

            # Append assistant turn with all content blocks
            messages.append({"role": "assistant", "content": self._build_assistant_content(response_text, tool_calls)})

            # Execute tools and build tool_result turn
            tool_results = []
            for tool_call in tool_calls:
                if stream:
                    console.print(f"\n[dim]  tool: {tool_call['name']}({self._summarise_input(tool_call['input'])})[/dim]")
                result = self.executor.execute(tool_call["name"], tool_call["input"])
                if stream:
                    preview = result[:200].replace("\n", " ")
                    console.print(f"[dim]  → {escape(preview)}{'...' if len(result) > 200 else ''}[/dim]")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        return final_text

    def _call(
        self, messages: list[dict[str, Any]], stream: bool
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """
        Send messages to Claude. Returns (text, stop_reason, tool_calls).
        Streams text output if stream=True. Retries on dropped connections.
        """
        system = [
            {
                "type": "text",
                "text": self.SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self._call_once(messages, stream, system)
            except httpx.RemoteProtocolError as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                console.print(f"\n[yellow]Connection dropped, retrying in {wait}s... ({e})[/yellow]")
                time.sleep(wait)

        raise RuntimeError("unreachable")

    def _call_once(
        self, messages: list[dict[str, Any]], stream: bool, system: list[dict[str, Any]]
    ) -> tuple[str, str, list[dict[str, Any]]]:
        collected_text = ""
        tool_calls: list[dict[str, Any]] = []
        stop_reason = "end_turn"

        if stream:
            with self.client.messages.stream(
                model=self.settings.model,
                system=system,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                tools=self.TOOLS,  # type: ignore[arg-type]
                max_tokens=self.settings.max_tokens,
            ) as s:
                for text in s.text_stream:
                    console.print(text, end="")
                    collected_text += text
                final = s.get_final_message()
            if collected_text:
                console.print()  # newline after streamed output
        else:
            final = self.client.messages.create(
                model=self.settings.model,
                system=system,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
                tools=self.TOOLS,  # type: ignore[arg-type]
                max_tokens=self.settings.max_tokens,
            )
            for block in final.content:
                if hasattr(block, "text"):
                    collected_text += block.text

        stop_reason = final.stop_reason or "end_turn"

        for block in final.content:
            if block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return collected_text, stop_reason, tool_calls

    @staticmethod
    def _build_assistant_content(
        text: str, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if text:
            content.append({"type": "text", "text": text})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            })
        return content

    @staticmethod
    def _summarise_input(inp: dict[str, Any]) -> str:
        parts = []
        for k, v in inp.items():
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:60] + "..."
            parts.append(f"{k}={v_str!r}")
        return ", ".join(parts)
