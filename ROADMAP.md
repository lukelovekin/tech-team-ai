# Roadmap

## v0.1 — Foundation (current)

- [x] 5 specialist agents: Developer, Reviewer, QA, Architect, Security
- [x] Streaming agentic loop with tool use
- [x] Prompt caching on system prompts
- [x] Full tool set: read, write, patch, list, search, git diff/log, shell
- [x] Shell blocklist safety guard + path traversal protection
- [x] Project context injection (README/CLAUDE.md, stack detection, git state)
- [x] `briefing/context.md` handoff — Architect writes structured context, all agents consume it
- [x] Pipeline mode (`tech-team run`) — fire-and-forget, all agents, writes `briefing/brief.md`
- [x] Collab mode (`tech-team collab`) — interactive loop, user confirms plan and final diff
- [x] Reviewer → Developer feedback loop in collab (loops until all agents satisfied or round cap)
- [x] Parallel analysis — Reviewer, QA, Security run concurrently via `ThreadPoolExecutor`
- [x] Two-tier model — Sonnet for Developer/Architect, Haiku for Reviewer/QA/Security
- [x] QA + Security skip on intermediate collab rounds (only run when reviewer is satisfied)
- [x] Round cap with unresolved findings saved to `briefing/brief.md`
- [x] Pre-commit hook mode with exit code blocking on `[CRITICAL]`
- [x] `tech-team install-hook` and `tech-team install-global-hook`
- [x] `tech-team check` — all analysis agents on unpushed commits or full repo
- [x] `tech-team fix` — review staged changes, offer developer fix before commit
- [x] `tech-team commit` — generate conventional commit messages for staged changes
- [x] `tech-team setup` — first-time API key setup with global config
- [x] `tech-team doctor` — validate Python, git, API key, live connection check
- [x] `tech-team init` — generate CLAUDE.md for any repo
- [x] `tech-team install-mcp` — register as MCP server in Claude Code
- [x] Retry on dropped connections (`httpx.RemoteProtocolError`, exponential backoff)
- [x] Global API key at `~/.config/tech-team/config` (chmod 600)

## v0.2 — Quality of life

- [ ] **Config file per project** — `.tech-team.toml` in the target repo for per-project agent
      behaviour tuning (e.g. skip certain checks, set language conventions)
- [ ] **Conversation mode** — multi-turn `tech-team chat` so you can iterate with an agent
      across multiple messages without starting fresh each time
- [ ] **Diff-only review** — smarter reviewer that focuses strictly on changed lines and only
      reads context files when they're directly relevant
- [ ] **Rich structured output** — reviewer and security output as structured JSON,
      renderable as tables with Rich
- [ ] **Token usage reporting** — show cost estimate per run and per pipeline

## v0.3 — Integrations

- [ ] **GitHub PR review** — `tech-team review --pr 123` fetches a PR diff from GitHub API
      and runs the reviewer agent against it, posts a review comment
- [ ] **Jira/Linear ticket reading** — `tech-team dev PROJ-123` fetches the ticket description
      automatically before handing to the developer agent
- [ ] **CI/CD mode** — structured output (JSON) with exit codes for each severity level,
      suitable for GitHub Actions / GitLab CI
- [ ] **Slack/webhook notifications** — pipeline completion notifications
- [ ] **`.github/workflows/tech-team.yml`** — example GitHub Actions workflow

## v0.4 — Agent improvements

- [ ] **Agent memory** — persistent notes per repo (patterns discovered, decisions made,
      known issues) that survive across invocations
- [ ] **Performance agent** — profiling, N+1 query detection, bundle size analysis
- [ ] **Documentation agent** — keeps README, docstrings, and API docs in sync with code changes
- [ ] **Dependency agent** — checks for outdated or vulnerable packages, suggests upgrades
- [ ] **Migration agent** — plans and executes database migrations alongside code changes

## v0.5 — Team workflow

- [ ] **Async pipeline** — long-running pipeline that runs in the background and notifies on
      completion (useful for large codebases)
- [ ] **Agent specialisation** — per-stack agent variants (e.g. a Django-specific developer
      agent vs a FastAPI-specific one) using the base + stack-specific prompt extension
- [ ] **Review templates** — configurable review checklists per team/project
- [ ] **Audit trail** — append-only log of all agent runs, outputs, and file changes for a repo

## Non-goals

These are intentionally out of scope:

- **Autonomous PR creation** — agents suggest and modify, humans commit and push
- **Production deployment** — agents work on local code, not remote infrastructure
- **Cross-repository orchestration** — each invocation targets one repo
