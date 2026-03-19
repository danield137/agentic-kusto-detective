# Copilot Instructions — Agentic Kusto Detective

## Project Overview

This is a lab and benchmark for letting AI agents autonomously solve [Kusto Detective Agency](https://detective.kusto.io/) challenges using KQL (Kusto Query Language). Season 1 has been fully solved. The project uses Python with the GitHub Copilot SDK and Claude Opus 4.6 (1M context).

**Long-term goals:**
- Scoreboard system where users upload their own agent configurations
- Agents are scored on **LLM call count** and **token usage** (lower is better)
- Season 1 cases are interlinked — agent memory/learnings carry over between cases

## Build & Run

```bash
# Install
python -m pip install -e ".[dev]"
python -m playwright install chromium

# Lint
python -m ruff check src/

# Test
python -m pytest tests/ -v

# Run agent (single iteration)
python run.py ralph --challenge-num 1 -i 1

# Run multi-iteration loop
python run.py ralph --challenge-num 1 -i 10
python run.py ralph --seed session_20260311_034640 --bundle detective-v2 -i 5

# Resume an interrupted session
python run.py resume <session_id>
```

### Environment Variables

- `GITHUB_TOKEN` — GitHub PAT for Copilot SDK
- `DETECTIVE_CLUSTER_URI` — Your free Kusto cluster URI for detective.kusto.io site login

## Architecture

- **Agent framework:** GitHub Copilot SDK — `CopilotClient` + `create_session()` with custom tools
- **Model:** Claude Opus 4.6 with 1M context (configured in `run.py`)
- **Agent bundles:** Declarative configs under `agents/bundles/{name}/` — each contains `prompt.md` (system prompt template), `config.json` (metadata + seed files), `skills/` (with scripts), `knowledge/`, and `mcps.json`
- **Bundle loader:** `src/detective/bundle_loader.py` — loads a bundle into an `AgentBundle` dataclass
- **Ralph:** `run.py` — single source of truth for all session logic. Contains the session engine (`run_session`, `resume_session`) and the multi-iteration loop that distills findings and seeds the next iteration
- **Kusto auth:** `DefaultAzureCredential` — uses locally signed-in Azure identity
- **Browser:** Playwright Chromium — agent reads challenges and submits answers via detective.kusto.io
- **Tools:** Defined with `@define_tool` decorator + Pydantic models for parameter schemas
  - `kusto_tools.py` — KQL queries and management commands
  - `browser_tools.py` — Playwright browser automation
  - `memory_tools.py` — Persistent memory across sessions
  - `reasoning_tools.py` — Hypothesis dependency tree (add/solidify/invalidate/show)
  - `handoff_tools.py` — Session-to-session handoff context
  - `expert_tools.py` — Consult a separate LLM when stuck
- **Action logging:** Every tool call logged to `sessions/session_*/session.jsonl` with args, results, duration, timestamps
- **Follow mode:** `--follow` streams reasoning + tool calls to stderr
- **Reflection checkpoints:** Every 20 tool calls the agent is forced to save memory and reflect on progress

## Conventions

- Python 3.11+, linted with ruff (100 char line length)
- Tools are in `src/detective/*_tools.py` — each file exports tool functions decorated with `@define_tool`
- Bundle tool scripts in `agents/bundles/{name}/skills/<skill>/scripts/*.py` import from `src/detective/*_tools.py` and re-export via `__tools__` lists
- All tools log their inputs/outputs via `action_log.get_log()` — new tools must do the same
- Keep agent logic modular: separate challenge-solving logic from scoring/telemetry infrastructure
- Agent bundles live in `agents/bundles/{name}/` — prompt, skills, knowledge, and MCP configs are content files, not code
- Tests live in `tests/` — run with `python -m pytest tests/ -v`

## Kusto / KQL Notes

- KQL is the query language for Azure Data Explorer; it is **not** SQL — do not confuse the two
- Use `.show tables`, `.show table <name> schema`, and `<table> | take 10` as standard exploration patterns
- The Kusto Detective Agency challenges provide their own clusters and databases
- Answers to detective challenges are submitted via the detective.kusto.io browser interface
