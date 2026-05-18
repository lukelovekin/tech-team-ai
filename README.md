# tech-team-ai

An AI software team you run from the terminal. Specialist Claude agents that operate on any
repository: implementing features, reviewing code, writing tests, planning architecture, and
auditing for security. All from a single `tech-team` command.

---

## Why this vs just prompting Claude?

When you prompt Claude directly you are the orchestrator. You route context between roles,
copy-paste output back in, and decide when it's good enough. tech-team automates that layer.

**What you get that you can't get from a chat prompt:**

- **Specialist depth:** each agent has a tuned system prompt encoding specific priorities.
  The reviewer checks correctness, regression risk, design patterns, redundancy, security,
  performance, and accessibility (ARIA, keyboard nav, focus management, `prefers-reduced-motion`).
  You'd have to write that prompt yourself every single time otherwise.

- **Real codebase access:** agents read your actual files, search across the repo with grep,
  run your test suite, and check git history. They work on the code, not a description of it.

- **Agentic loops:** one agent run is many steps. Read existing patterns, write code, run
  tests, fix failures, check diff. A chat response is one shot.

- **Multi-agent review:** `collab` chains specialists so the reviewer catches what the
  developer missed, QA covers what the reviewer didn't think to test, and security audits the
  final state. That's normally a team of people. You get it as one command.

- **Automatic scope:** `check` knows exactly which commits haven't been pushed and focuses
  agents on just those changes. `fix` knows what's staged. Chat has no concept of your git state.

- **Built into the commit flow:** the global pre-commit hook means review and security run
  on every commit across every repo without you remembering to ask.

The force multiplier: you express intent once, agents do multi-step multi-perspective work,
you see the diff and confirm. The cognitive overhead of orchestrating that manually disappears.

---

## Two ways to work

**Path A: you write the code, agents review it**

```
write code  ->  git add  ->  tech-team fix  ->  git commit
                                  |
                      reviews staged changes
                      if issues found: offers to fix automatically
                      if clean: "ready to commit"
```

The pre-commit hook does the same check automatically on every `git commit`.
Use `tech-team fix` to resolve issues interactively before the hook fires.

**Path B: agents write the code, you confirm**

```
tech-team collab "task"  ->  git add  ->  git commit
        |
  architect plans, you approve
  developer implements
  reviewer + QA + security loop until all satisfied
  full diff shown, you confirm before anything is kept
```

Both paths lead to the same place: a clean, reviewed commit. Choose based on whether you
want to write the code yourself or hand it to the agents.

---

## Will this work on my machine / can I fork it?

Yes. Fork, clone, and run locally:

```bash
git clone <fork-url>
cd tech-team-ai
python3 -m venv venv && source venv/bin/activate
pip install -e .
cp .env.example .env
# set ANTHROPIC_API_KEY
tech-team --help
```

**API key, not Claude.ai subscription:** this calls the Anthropic API directly, which is
separate from a claude.ai subscription. You need an API key from
[console.anthropic.com](https://console.anthropic.com). If you already use Claude Code you
likely have API access, but it's a separate billing line from the claude.ai subscription.

**Cost:** agents are pay-per-use (token-based). A single `review` or `dev` on a small
change is cheap. A `collab` run with 5 rounds and 4 agents on a large feature is not trivial.
Prompt caching is applied to all system prompts, which reduces cost on the multi-turn
tool-use loops, but set expectations before running `collab` on a 3000-line file.

**Platform:** works on Mac and Linux. Windows users need WSL or Git Bash (the pre-commit
hook scripts are bash). Python 3.11+ required.

---

## Agents

| Agent | Triggered by | What it does |
|---|---|---|
| **Developer** | `dev`, `collab`, `run` | Reads existing patterns first, writes matching code, runs tests |
| **Reviewer** | `review`, `check`, `pre-commit`, `collab` | Code quality, design patterns, regression risk, **accessibility** |
| **QA** | `qa`, `check`, `collab`, `run` | Writes tests for edge cases and failure paths, not just coverage numbers |
| **Architect** | `plan`, `dev --plan`, `collab`, `run` | Plans before code is written, writes ADRs for significant decisions |
| **Security** | `audit`, `check`, `pre-commit`, `collab` | OWASP checks, secrets detection, injection risks, auth gaps |

---

## Task template

`task.template.md` is an optimised prompt structure for `collab` and `dev --plan`. Copy
it into your project, fill in what you know, and leave the rest blank.

```bash
cp ~/tech-team-ai/task.template.md ./TASK.md
# fill in Task (required) and anything else you know
tech-team collab "$(cat TASK.md)"
```

**Blank fields are intentional.** Any section you leave empty — stack, database, auth,
data model — the Architect fills in with an opinionated default and surfaces it at the top
of the plan under **Assumed defaults** before any code is written:

```
## Assumed defaults
- Language / framework: FastAPI — lightweight, async, auto-docs; right for REST APIs
- Database: SQLite via SQLAlchemy — zero-config, right-sized for a single-server app
- Auth: JWT (python-jose) — stateless, no session store needed
```

You see every assumption at the plan confirmation step and can redirect before the
developer touches a single file.

---

## briefing/ — session scratchpad

Every `collab`, `run`, and `check --report` session writes a gitignored `briefing/` folder
in the target repo. It's a scratchpad for the human — never committed, never shown in diffs.

```
briefing/
  design.md   # Architect's plan + key decisions (written before any code)
  brief.md    # End-of-session combined output: plan, review, QA, security
```

**`briefing/design.md`** is written by the Architect before implementation starts. It contains
the full implementation plan plus a **Key decisions** section for every non-trivial call:

```
### <decision title>
Chose: <what was selected>
Considered: <realistic alternatives>
Why: <the specific constraint or tradeoff>
Next-best: <what to do if this turns out to be wrong>
```

This is the "senior sign-off" view — everything a senior engineer would want to understand
and potentially challenge before the first line of code is written.

**`briefing/brief.md`** is the end-of-session combined brief: architect plan, code review
findings, QA analysis, and security audit. The brief from the final round is kept, so it
reflects the state of the code after any developer fix cycles.

Both files are overwritten each session. If you want to preserve a session's output, copy it
out before running again.

---

## Install

```bash
git clone git@github.com:lukelovekin/tech-team-ai.git
cd tech-team-ai
python3 -m venv venv && source venv/bin/activate
pip install -e .

cp .env.example .env
# open .env and set ANTHROPIC_API_KEY=sk-ant-...
```

### First run

Activate the venv and verify everything is wired up:

```bash
source ~/tech-team-ai/venv/bin/activate
tech-team --help
```

The `tech-team` command is now available in any terminal session where the venv is active.
To use it from any repo without manually activating first, add this to your shell profile
(`~/.zshrc` or `~/.bashrc`):

```bash
source ~/tech-team-ai/venv/bin/activate
```

Then try it on any repo you have locally:

```bash
cd ~/your-project
tech-team review          # reviewer reads your working tree
tech-team check           # all agents on your unpushed commits
```

Or point it at a path directly without changing directory:

```bash
tech-team review --repo ~/your-project/src/
tech-team check --repo ~/your-project --base main
```

---

## Commands

### `dev`

Implement a feature or fix from a prompt.

```bash
tech-team dev "add rate limiting to the /api/chat endpoint"
tech-team dev "fix the N+1 query in UserService.list()"
```

Use `--plan` to run the Architect first. It produces a structured implementation plan,
you confirm it, then the Developer follows it. Good for anything non-trivial.

```bash
tech-team dev "add OAuth login" --plan
```

For a full iterative cycle with review feedback, use `collab` instead.

---

### `review`

Code review: correctness, regression risk, design pattern consistency, redundancy,
security, performance, maintainability, and **accessibility** (semantic HTML, ARIA, keyboard
navigation, focus management, colour contrast considerations, `prefers-reduced-motion`).

Findings are labelled `[CRITICAL]` / `[WARNING]` / `[INFO]` with a concrete suggested fix for each.

```bash
tech-team review                   # review working tree changes
tech-team review --staged          # review only staged changes
tech-team review src/auth/         # review a specific path
```

---

### `qa`

Analyse test coverage and write or improve tests.

Reads existing test patterns and fixtures first, then writes tests that cover edge cases,
error paths, and boundary conditions rather than just happy paths.

```bash
tech-team qa                       # analyse coverage across the repo
tech-team qa src/payments/         # focus on a specific module
```

---

### `plan`

Architecture planning before any code is written.

Returns a structured plan: files to change/create, implementation steps, risks, open questions.
Writes ADRs to `docs/adr/` for significant decisions. Use this before `dev` on anything large,
or use `dev --plan` to chain them automatically.

```bash
tech-team plan "migrate from REST to GraphQL for the user service"
tech-team plan "add multi-tenancy to the billing module"
```

---

### `audit`

Security audit: OWASP Top 10, hardcoded secrets, injection vectors, missing auth, weak crypto.

Findings are labelled `[CRITICAL]` / `[HIGH]` / `[MEDIUM]` / `[LOW]`.

```bash
tech-team audit                    # audit working tree changes
tech-team audit --staged           # audit staged changes
tech-team audit src/api/           # audit a specific path
```

---

### `check`

The most useful day-to-day command. Runs Reviewer + QA + Architect + Security against your
unpushed commits before you push.

```bash
tech-team check                    # diff of unpushed commits vs remote tracking branch
tech-team check --base main        # diff vs main (useful before opening a PR)
tech-team check --full             # analyse the entire repo
```

Scope resolution when no `--base` is given:
1. `git diff <remote-tracking>..HEAD` (commits not yet pushed)
2. Falls back to `git diff HEAD~1..HEAD` if no tracking branch exists

Skip individual agents or save a report:

```bash
tech-team check --no-arch --no-qa          # just review + security
tech-team check --base main --report       # full check vs main, write briefing/brief.md
tech-team check --full --no-arch           # whole repo, skip architect
```

---

### `collab`

Agents iterate on each other's output until all are satisfied, then you see the full diff
and confirm before anything is kept.

```bash
tech-team collab "add user authentication"
tech-team collab "refactor the payment service" --max-rounds 3
tech-team collab "add rate limiting" --no-plan --no-audit
tech-team collab "build a todo API" --repo ~/new-project --init
```

Use `--init` when starting a brand-new project. It runs `git init` in the target directory
(creating it if needed) so you don't have to set up the repo manually first.

**Flow:**

```
1. Architect plans, you approve the plan
   (zero files written yet, safe to bail here)

2. Developer implements

3. Reviewer + QA + Security analyse
   findings labelled [CRITICAL] / [WARNING]

4. If issues found: Developer fixes, back to step 3
   Repeats up to --max-rounds (default: 5)

5. All agents satisfied, full diff shown

6. "Apply these changes? [y/N]"
   Yes: changes stay in working tree, commit normally
   No:  git reverts everything cleanly
```

| Flag | Default | Effect |
|---|---|---|
| `--max-rounds` | 5 | Maximum fix iterations before stopping |
| `--no-plan` | off | Skip architect phase, go straight to developer |
| `--no-qa` | off | Skip QA in the review loop |
| `--no-audit` | off | Skip security in the review loop |

---

### `fix`

The interactive companion to the pre-commit hook. Run it before committing to catch issues
and, if any are found, let the developer agent fix them for you.

```bash
git add <files>
tech-team fix          # review + optionally fix
git commit
```

Flow:
1. Reviewer and Security analyse your staged changes
2. If clean, "ready to commit"
3. If issues found, shows findings and asks "Run developer to fix these?"
4. Yes: developer fixes on top of your staged work, shows diff
5. "Apply fixes and re-stage? [y/N]": yes re-stages, no reverts the agent's changes
6. Your original staged work is never touched

```bash
tech-team fix --no-audit    # skip security, review only
```

---

### `commit`

Generate a conventional commit message for staged changes and commit.

```bash
git add src/auth.py tests/test_auth.py
tech-team commit               # generate message, confirm, commit
tech-team commit --dry-run     # preview message only
```

Produces messages in the format `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `style:`, `perf:`.
You can accept the suggestion, edit it, or reject it.

---

### `run`

Fire-and-forget pipeline: chains all agents without pausing for confirmation and writes
`briefing/brief.md` at the end.

```bash
tech-team run "JIRA-123: add password reset flow"
tech-team run "add caching layer" --no-plan --no-qa
```

Use `collab` instead when you want to review and approve changes before they're finalised.

---

### Targeting a different repo

Every command accepts `--repo` to point at any directory:

```bash
tech-team review --repo ../my-other-project
tech-team check --repo ~/projects/api-service --base main
tech-team collab "add dark mode" --repo ~/projects/frontend
```

---

## Pre-commit hooks

### Global hook (runs on every repo on this machine)

```bash
tech-team install-global-hook
```

Sets `git config --global core.hooksPath` and installs a hook that runs Reviewer + Security
on every commit across all your repos. Uses the full binary path so no venv activation needed.

```bash
git commit --no-verify          # bypass for one commit
touch .no-tech-team             # opt this repo out permanently
tech-team remove-global-hook    # remove entirely
```

> `core.hooksPath` replaces `.git/hooks/` globally. Per-repo hooks in `.git/hooks/` won't
> fire while the global path is set. Use `--no-verify` or `.no-tech-team` for exceptions.

### Per-repo hook

```bash
tech-team install-hook          # installs into .git/hooks/pre-commit
rm .git/hooks/pre-commit        # remove
```

The hook exits `1` on any `[CRITICAL]` finding, blocking the commit.

---

## Claude Code MCP integration

Register tech-team as an MCP server so you can invoke agents mid-conversation in Claude Code:

```bash
tech-team install-mcp
# then restart Claude Code
```

Available tools after registration:

| Tool | What it does |
|---|---|
| `developer` | Implement a feature or fix |
| `reviewer` | Review code for quality, patterns, accessibility |
| `qa_engineer` | Analyse and improve test coverage |
| `architect` | Plan before coding |
| `security` | Security audit |
| `check` | All analysis agents on recent changes or full repo |

Example in a Claude Code conversation:
> "Use the architect tool to plan adding a Redis cache layer to my FastAPI app, then use the
> developer tool to implement it"

Start the server manually:

```bash
tech-team mcp
```

---

## Workflow guide

| Situation | Command |
|---|---|
| Quick fix or small feature | `tech-team dev "..."` |
| Non-trivial feature, want a plan first | `tech-team dev "..." --plan` |
| Full iterative cycle with approval | `tech-team collab "..."` |
| You wrote code, want it reviewed before committing | `tech-team fix` |
| Before pushing a branch | `tech-team check` |
| Before opening a PR against main | `tech-team check --base main` |
| Periodic full repo health check | `tech-team check --full --report` (writes `briefing/brief.md`) |
| Dedicated test pass | `tech-team qa` |
| Reviewing someone else's code | `tech-team review src/their-module/` |
| Fire-and-forget ticket implementation | `tech-team run "TICKET-123: ..."` |

---

## How agents work

Each agent is a Claude API call with:
- A specialist system prompt defining role, priorities, and output format
- Tools: `read_file`, `write_file`, `patch_file`, `list_directory`, `search_code`,
  `get_git_diff`, `get_git_log`, `run_shell`
- An agentic loop where tool calls are executed and fed back until the agent is done

Output streams in real time. Tool calls are shown inline so you can see exactly what the
agent is reading and writing.

**Project context** is gathered automatically before each run: README or CLAUDE.md (first
3000 chars), detected tech stack, top-level directory structure, current branch, and recent
commits. Agents start oriented, not cold.

**Prompt caching** is applied to all system prompts, reducing cost and latency on the
multi-turn tool-use loops that make up each agent run.

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | | Anthropic API key |
| `TECH_TEAM_MODEL` | no | `claude-sonnet-4-6` | Model for all agents |
| `TECH_TEAM_MAX_TOKENS` | no | `8192` | Max tokens per response |
| `TECH_TEAM_TIMEOUT` | no | `120` | Shell command timeout (seconds) |

---

## Safety

Shell commands are filtered through a blocklist before execution. Permanently blocked:

- `rm -rf`
- `git push`, `git reset --hard`, `git checkout --`, `git clean -f`
- `sudo`
- `curl | sh`, `wget | bash`, `dd if=`

All file operations are path-traversal guarded so agents cannot read or write outside the
target repo root.

**Write permissions by agent:**

| Agent | Reads | Writes files | Runs shell |
|---|---|---|---|
| Developer | yes | yes | yes |
| Reviewer | yes | no | yes (read-only cmds) |
| QA | yes | yes | yes |
| Architect | yes | yes (ADRs, docs) | yes |
| Security | yes | no | yes (read-only cmds) |

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check src/ tests/
mypy src/
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design and [ROADMAP.md](ROADMAP.md) for planned features.
