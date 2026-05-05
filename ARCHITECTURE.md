# Architecture

## Core design

Each agent is a thin wrapper around a single Claude API call with tool use. The `BaseAgent`
class owns the agentic loop — subclasses only define:

- `SYSTEM_PROMPT` — the agent's role, behaviour, and output format
- `TOOLS` — which tools from the registry the agent is allowed to use
- `ALLOW_WRITES` — whether the tool executor permits file writes

```
CLI command
    │
    ▼
agent.run(task, extra_context)
    │
    ├─ context.gather(repo_path)   ← README, CLAUDE.md, stack detection, git log
    │
    └─ BaseAgent.run()
           │
           ├─ client.messages.stream(system, messages, tools)
           │         ↑ prompt caching on system prompt
           │
           ├─ stream text to terminal
           │
           ├─ [stop_reason == tool_use]
           │       │
           │       └─ ToolExecutor.execute(tool_name, input)
           │               ├─ read_file / list_directory / search_code
           │               ├─ get_git_diff / get_git_log
           │               ├─ run_shell (with blocklist)
           │               ├─ write_file / patch_file (write agents only)
           │               └─ path traversal guard on all file ops
           │
           └─ loop until stop_reason == end_turn
```

## Agent permissions

| Agent | Reads files | Writes files | Runs shell |
|---|---|---|---|
| Developer | yes | yes | yes |
| Reviewer | yes | no | yes (read-only cmds) |
| QA | yes | yes | yes (test runners) |
| Architect | yes | yes (ADRs/docs) | yes |
| Security | yes | no | yes (read-only cmds) |

All agents use the same shell blocklist regardless of permissions.

## Pipeline mode

`tech-team run` chains agents sequentially, passing each agent's output as context to the next:

```
Architect output → Developer input (as plan)
Developer output → Reviewer input (as implementation summary)
Developer output → QA input
Developer output → Security input
All outputs      → tech-team-report.md
```

Agents share `project_context` (gathered once before the pipeline starts) but do not share
message history — each agent starts fresh.

## Project context

`context.py` gathers a lightweight project snapshot before each agent run:

1. CLAUDE.md or README.md (first 3000 chars)
2. Detected tech stack (pyproject.toml, package.json, go.mod, etc.)
3. Top-level directory listing
4. Current git branch + 5 most recent commits

This is injected as a prefix to the user's task. It costs tokens but prevents agents from
exploring blindly and dramatically improves first-tool-call accuracy.

## Tool safety

`ToolExecutor` enforces:

- **Path traversal guard** — all file paths are resolved and checked against `repo_path`
  before any read or write operation
- **Write guard** — `write_file` and `patch_file` check `allow_writes` and return an error
  rather than raising if the agent shouldn't have write access
- **Shell blocklist** — a list of dangerous command patterns is checked before any `subprocess`
  call; matched commands return an error string without executing
- **Output truncation** — shell output and search results are capped at 10,000 chars / 200 lines
  to prevent token blowout

## Prompt caching

System prompts use `cache_control: {"type": "ephemeral"}` (5-minute TTL). This reduces cost and
latency on multi-turn conversations (tool-use loops) where the system prompt is unchanged.

## Key files

| File | Purpose |
|---|---|
| `agents/base.py` | Agentic loop, streaming, tool dispatch |
| `agents/*.py` | System prompts and tool permissions per agent |
| `tools/registry.py` | Tool schema definitions (Anthropic format) |
| `tools/executor.py` | Tool execution, safety guards, subprocess calls |
| `context.py` | Project context gathering |
| `orchestrator.py` | Pipeline mode, inter-agent context passing |
| `cli.py` | Typer CLI, command definitions, hook installation |
| `config.py` | Pydantic Settings, repo root detection |
