# Roadmap

## v0.1 — Foundation (current)

- [x] 5 specialist agents: Developer, Reviewer, QA, Architect, Security
- [x] Streaming agentic loop with tool use
- [x] Prompt caching on system prompts
- [x] Full tool set: read, write, patch, list, search, git diff/log, shell
- [x] Shell blocklist safety guard + path traversal protection
- [x] Project context injection (README/CLAUDE.md, stack detection, git state)
- [x] Pipeline mode: all agents in sequence with shared context
- [x] Pre-commit hook mode with exit code
- [x] `tech-team install-hook` for one-command hook setup
- [x] `tech-team-report.md` output from pipeline runs

## v0.2 — Quality of life

- [ ] **Config file per project** — `.tech-team.toml` in the target repo for per-project agent
      behaviour tuning (e.g. skip certain checks, set language conventions)
- [ ] **Conversation mode** — multi-turn `tech-team chat` so you can iterate with an agent
      across multiple messages without starting fresh each time
- [ ] **Diff-only review** — smarter reviewer that focuses strictly on changed lines and only
      reads context files when they're directly relevant
- [ ] **Parallel agent execution** — run reviewer + security concurrently in pipeline mode
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
- [ ] **Reviewer → Developer feedback loop** — if reviewer finds CRITICAL issues, automatically
      re-invoke the developer to fix them before moving to QA
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
