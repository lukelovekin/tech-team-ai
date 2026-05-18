# tech-team-ai

AI software team — a set of specialist Claude agents that operate on any target repo from the CLI.

## What this repo is

A Python package (`tech_team`) that exposes a `tech-team` CLI. Each command invokes a specialist agent
backed by the Anthropic SDK. Agents use tool calls to read/write files, run shell commands, and query
git in the target repository (defaulting to the current working directory).

## Stack

- Python 3.11+ with strict type hints
- Anthropic SDK (`anthropic`) — claude-sonnet-4-6, streaming, prompt caching
- Typer + Rich — CLI and terminal output
- Pydantic Settings — config and env management
- pytest — tests in `tests/`

## Repo layout

```
src/
  cli.py             # Typer app, all CLI commands
  config.py          # Settings (pydantic-settings, global config)
  orchestrator.py    # Fire-and-forget pipeline: plan → dev → review/qa/security (parallel)
  collab.py          # Interactive loop: architect → dev → analysis → confirm
  context.py         # Reads target repo to build project context for agents
  mcp_server.py      # MCP server (stdio) for Claude Code integration
  agents/
    base.py          # BaseAgent: tool-use loop, streaming, retry, prompt caching
    developer.py     # Implements features and fixes
    reviewer.py      # Code quality, patterns, regression risk
    qa.py            # Test coverage and quality
    architect.py     # System design, ADRs, implementation planning
    security.py      # OWASP checks, secrets detection, auth review
  tools/
    registry.py      # Tool schema definitions for the Anthropic API
    executor.py      # Tool dispatch and execution with safety guards
tests/
  test_agents.py
```

## Running locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # add your ANTHROPIC_API_KEY
tech-team --help
```

## Key conventions

- Agents are stateless per invocation — no shared memory between calls
- `BaseAgent.run()` owns the agentic loop; subclasses define `SYSTEM_PROMPT`, `TOOLS`, `ALLOW_WRITES`
- `BaseAgent.__init__` accepts `model: str | None` — pass `settings.analysis_model` for analysis agents
- Tool execution lives entirely in `tools/executor.py` — agents never call subprocess directly
- Dangerous shell commands (rm -rf, git push, git reset --hard, sudo) are blocked at executor level
- All output goes through Rich — use `console.print()`, never bare `print()`
- Prompt caching: system prompts use `cache_control: {"type": "ephemeral"}`
- Reviewer, QA, Security run in parallel via `ThreadPoolExecutor` in both `collab.py` and `orchestrator.py`
- In `collab` mode, QA and Security only run when the reviewer is satisfied or `max_rounds` is reached

## Adding a new agent

1. Create `src/tech_team/agents/your_agent.py`, subclass `BaseAgent`
2. Define `SYSTEM_PROMPT`, `TOOLS` (subset of registry), `ALLOW_WRITES`
3. Add a command to `cli.py`
4. Register in `orchestrator.py` if it should be part of the pipeline

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `TECH_TEAM_MODEL` | no | `claude-sonnet-4-6` | Model for Developer and Architect agents |
| `TECH_TEAM_ANALYSIS_MODEL` | no | `claude-haiku-4-5-20251001` | Model for Reviewer, QA, and Security agents |
| `TECH_TEAM_MAX_TOKENS` | no | `8192` | Max tokens per response |
| `TECH_TEAM_SHELL_TIMEOUT` | no | `120` | Shell command timeout (seconds) |

Stored in `~/.config/tech-team/config` (created by `tech-team setup`) or local `.env`.

## Tests

```bash
pytest tests/ -v
```

Tests mock the Anthropic client — no real API calls in the test suite.
