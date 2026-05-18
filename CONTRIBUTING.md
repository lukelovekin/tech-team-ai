# Contributing

## Setup

```bash
git clone https://github.com/lukelovekin/tech-team-ai
cd tech-team-ai
python3.12 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
tech-team setup    # saves API key to ~/.config/tech-team/config
```

## Running tests

```bash
pytest tests/ -v
```

Tests mock the Anthropic client — no real API calls, no cost.

## Adding a new agent

1. Create `src/agents/your_agent.py`, subclass `BaseAgent`
2. Define `SYSTEM_PROMPT`, `TOOLS` (from `src/tools/registry.py`), `ALLOW_WRITES`
3. If it's an analysis agent (read-only), pass `model=settings.analysis_model` when instantiating it — this uses Haiku instead of Sonnet
4. Add a command to `src/cli.py`
5. Add to `src/orchestrator.py` and/or `src/collab.py` if it belongs in the pipeline
6. Write tests in `tests/test_agents.py`

```python
from src.agents.base import BaseAgent
from src.tools.registry import READONLY_TOOLS

class MyAgent(BaseAgent):
    SYSTEM_PROMPT = "You are ..."
    TOOLS = READONLY_TOOLS
    ALLOW_WRITES = False

    @property
    def name(self) -> str:
        return "MyAgent"
```

## Code conventions

- Type hints on everything
- No bare `print()` — use `console.print()` from Rich
- No new dependencies without discussion
- Tests for any new executor behaviour or agent infrastructure

## Releasing

Bump the version in `pyproject.toml`, then:

```bash
git tag v0.x.0
git push origin v0.x.0
```

GitHub Actions publishes to PyPI automatically.
