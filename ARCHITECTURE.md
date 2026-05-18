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

## Pipeline mode (`tech-team run`)

Fire-and-forget: chains agents, no confirmation prompts.

```
Architect → Developer → ┬─ Reviewer  ─┐
                        ├─ QA         ─┤ parallel (ThreadPoolExecutor)
                        └─ Security   ─┘
                                       └─ briefing/brief.md
```

Reviewer, QA, and Security run in parallel using `ThreadPoolExecutor(max_workers=3)` with
`stream=False`. Results are printed sequentially after all three complete.
Agents share `project_context` but not message history — each starts fresh.

## Collab mode (`tech-team collab`)

Interactive loop with user confirmation at start and end.

```
Architect → [user confirms plan]
              │
              └─ loop (max_rounds, default 2):
                   Developer
                   Reviewer  (streaming, always)
                   if reviewer clean OR last round:
                     QA + Security (parallel, no stream)
                   if all clean → break
              │
              └─ [user confirms diff] → apply or revert
```

QA and Security are skipped on intermediate rounds where the reviewer still finds issues —
they only run when the code is worth a full analysis pass. This saves significant time and
cost on builds that need multiple developer iterations.

Unresolved findings at the round limit are printed on screen and written to `briefing/brief.md`.

## Project context

`context.py` gathers a lightweight project snapshot before each agent run:

1. `briefing/context.md` if present — structured handoff written by the Architect agent
2. Otherwise: CLAUDE.md or README.md (first 3000 chars) + entry point file contents
3. Detected tech stack (pyproject.toml, package.json, go.mod, etc.)
4. Top-level directory listing
5. Current git branch + 5 most recent commits

In `collab` mode the Architect writes `briefing/context.md` before the developer starts.
`context.gather()` is called again after the Architect runs, so all subsequent agents
receive the structured handoff instead of re-exploring the codebase from scratch.

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
| `agents/base.py` | Agentic loop, streaming, retry on dropped connections, prompt caching |
| `agents/*.py` | System prompts and tool permissions per agent |
| `tools/registry.py` | Tool schema definitions (Anthropic format) |
| `tools/executor.py` | Tool execution, safety guards, subprocess calls |
| `context.py` | Project context gathering, `briefing/context.md` handoff |
| `collab.py` | Interactive loop, parallel analysis, round-cap logic, brief writing |
| `orchestrator.py` | Fire-and-forget pipeline, parallel analysis |
| `mcp_server.py` | MCP stdio server for Claude Code integration |
| `cli.py` | Typer CLI, all commands, hook installation, setup/doctor/init |
| `config.py` | Pydantic Settings, global config (`~/.config/tech-team/config`) |
