# Agentic Kusto Detective

An AI agent that autonomously solves [Kusto Detective Agency](https://detective.kusto.io/) challenges using KQL (Kusto Query Language). The agent reads challenge pages through a browser, explores data with KQL queries, reasons through puzzles using a structured hypothesis tree, and submits answers — all without human intervention.

**Season 1: Complete.** The agent solved all Season 1 cases end-to-end.

Built with the [GitHub Copilot SDK](https://github.com/github/copilot-sdk) and Claude Opus 4.6 (1M context).

## Quick Start

```bash
# Install dependencies
python -m pip install -e ".[dev]"
python -m playwright install chromium
cd web && npm install && cd ..

# Set your free Kusto cluster URI (used for site login)
# Windows
set DETECTIVE_CLUSTER_URI=https://yourcluster.region.dev.kusto.windows.net/
# Linux/macOS
export DETECTIVE_CLUSTER_URI=https://yourcluster.region.dev.kusto.windows.net/
```

Azure auth uses `DefaultAzureCredential` — sign in via Azure CLI (`az login`) or VS Code.

### Run the agent

```bash
# Single iteration on challenge 1
python run.py ralph --challenge-num 1 -i 1

# Multi-iteration loop (auto-seeds each from the last)
python run.py ralph --challenge-num 1 -i 10

# Seed from a specific session
python run.py ralph --seed session_20260311_034640 -i 5

# Use a different bundle
python run.py ralph --bundle detective-v2 -i 10

# Resume an interrupted session
python run.py resume session_20260311_034640
```

Each iteration:
1. Starts a fresh session, seeded with the previous session's findings
2. Agent works on the challenge until it completes or times out
3. Session artifacts are distilled into a structured summary (confirmed/invalidated hypotheses, key findings, memory)
4. The distilled summary seeds the next iteration
5. Stops early if the challenge is solved

### Run the web dashboard

```bash
# Start backend + frontend
python start.py
```

Open **http://localhost:5173** — the dashboard shows past sessions with stats (tool calls, wall-clock time, LLM time) and a button to kick off new runs with live SSE streaming.

## How It Works

### Tools

The agent has six categories of tools:

| Category | Tools | Purpose |
|----------|-------|---------|
| **Kusto** | `kusto_query`, `kusto_command` | Execute KQL queries and management commands |
| **Browser** | navigate, click, fill, screenshot, get content | Read challenges from detective.kusto.io, submit answers |
| **Memory** | `recall_memory`, `save_memory` | Persist learnings across sessions (schema, patterns, solutions) |
| **Reasoning** | `add_assumption`, `solidify`, `invalidate`, `show_tree` | Track hypotheses as a dependency tree |
| **Handoff** | `write_handoff` | Write structured summaries for session continuation |
| **Expert** | `ask_expert` | Consult a separate LLM when stuck |

### Reasoning Tree

The agent tracks its investigation as a dependency graph of hypotheses. Each node has a status:

- **HYPOTHESIS** — untested idea
- **SOLID** — confirmed with evidence
- **PARTIAL** — near-miss, needs investigation
- **INVALID** — disproven (auto-collapses all dependent nodes)

This prevents the agent from going in circles — invalidating a hypothesis automatically removes all downstream work that depended on it, forcing exploration of alternative branches.

### Agent Workflow

1. **Recall memory** from previous sessions
2. **Log in** to detective.kusto.io with the cluster URI
3. **Find the first unsolved case** in the inbox
4. **Read the challenge** and training materials
5. **Decompose** into sub-challenges with the reasoning tree
6. **Solve** each sub-challenge: Plan → Act → Observe → Reflect
7. **Submit** the answer through the browser
8. **Save memory** — always, whether solved or not

### Agent Bundles

Agent behavior is configured through **bundles** — declarative directories containing the system prompt, skills, knowledge base, and MCP server configs:

```
agents/bundles/detective-v1/
├── config.json              # Bundle metadata and seed file list
├── prompt.md                # System prompt template
├── mcps.json                # MCP server configurations
├── knowledge/               # Knowledge base files injected into context
│   └── memory-template.md
└── skills/
    ├── detective-kusto/      # KQL investigation skill
    │   └── scripts/          # Tool implementations
    └── plan-act-observe-reflect/  # Reasoning framework
```

Two bundles are included:
- **detective-v1** — Base configuration with KQL + reasoning tools
- **detective-v2** — Extended with image analysis capability

## Session Artifacts

Every run produces a session directory under `sessions/`:

```
sessions/session_20260312_232009/
├── session.jsonl            # Full action log (tool calls, agent messages, usage)
├── session_state.json       # Session metadata and status
├── challenge.md             # Challenge text from detective.kusto.io
├── memory.md                # Agent's accumulated knowledge
├── reasoning_tree.json      # Hypothesis tree state
├── worklog.md               # Running log of actions and results
├── handoff.md               # Structured summary for session continuation
├── iteration_summary.md     # Distilled findings for the Ralph loop
└── tasks.md                 # Agent's task checklist
```

Inspect a session log:
```powershell
Get-Content sessions\session_*\session.jsonl | ConvertFrom-Json | Format-Table event, tool, elapsed_s, duration_s
```

## Follow Mode

Use `--follow` (or `-f`) to stream the agent's execution live:
- Agent reasoning and messages stream token-by-token to stderr
- Tool calls print with arguments and results as they happen

## Project Structure

```
src/detective/
├── main.py              # CLI entry point
├── runner.py            # Session executor (loads bundle, manages Copilot SDK lifecycle)
├── bundle_loader.py     # Loads agent bundles into AgentBundle dataclass
├── kusto_tools.py       # KQL query and command tools
├── memory_tools.py      # Persistent memory (read/write memory.md)
├── reasoning_tools.py   # Hypothesis tree (add/solidify/invalidate/show)
├── handoff_tools.py     # Session-to-session handoff context
├── action_log.py        # JSON-lines action logger
├── log_parser.py        # JSONL log file parser
├── session_context.py   # Per-session directory management
├── session_state.py     # Session state persistence
├── server.py            # FastAPI web server with SSE
└── season.py            # Season-level orchestration

run.py                 # Multi-iteration loop with session distillation
start.py                 # Start web dashboard (backend + frontend)
generate_report.py       # Markdown report from session logs

agents/bundles/          # Declarative agent configurations
web/                     # React + TypeScript dashboard (Vite)

tests/
├── test_server.py       # Local server mimicking detective.kusto.io
├── test_e2e.py          # E2E pytest tests (@pytest.mark.llm)
├── run_isolated.py      # Standalone: one session per challenge
├── setup_kusto.py       # Create test tables in Kusto cluster
├── challenges.json      # Synthetic challenge definitions
└── conftest.py          # pytest config (--run-llm flag)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub PAT for Copilot SDK |
| `DETECTIVE_CLUSTER_URI` | Yes | Your free Azure Data Explorer cluster URI |
| `DETECTIVE_HEADLESS` | No | Set to `true` for headless Playwright (default: `false`) |

## Testing

The project includes an E2E test harness that runs the agent against synthetic challenges on a local server mimicking detective.kusto.io.

### Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Test Runner │────>│  Local Server    │     │  Kusto Cluster   │
│  (pytest)    │     │  (FastAPI)       │     │  (MyDatabase)    │
│              │     │                  │     │                  │
│  One session │     │  /inbox          │     │  Numbers table   │
│  per case    │     │  /inbox/<slug>   │     │  Cities table    │
│              │     │  /submit         │     │                  │
└──────┬───────┘     └──────────────────┘     └────────▲─────────┘
       │                                               │
       │         ┌──────────────────┐                  │
       └────────>│  Agent           │──────────────────┘
                 │  (Copilot SDK)   │  KQL queries
                 │                  │
                 │  Playwright ─────┘  Browser automation
                 └──────────────────┘
```

The agent navigates the local server with Playwright (same as it would detective.kusto.io), reads challenge pages, queries the Kusto cluster for answers, and submits via the browser.

### Synthetic challenges

Three challenges are defined in `tests/challenges.json`:

| # | Challenge | Type | Answer |
|---|-----------|------|--------|
| 1 | Number Crunch | Query `Numbers` table for F(100), extract 2nd digit | `5` |
| 2 | Timezone Twist | Query `Cities` table for max European timezone diff | `3` |
| 3 | The Final Count | Arithmetic: (answer1 + answer2) × 3 | `24` |

### Metric isolation

Each challenge runs in its own session via the `task` parameter, which scopes the agent's initial prompt to a single challenge. This gives clean per-challenge metrics (tokens, time, cost, tool calls) without post-hoc splitting.

### Setup

```bash
# 1. Install dependencies
python -m pip install -e ".[dev]"
python -m playwright install chromium

# 2. Create test data in your Kusto cluster
python tests/setup_kusto.py

# 3. Start the test server (keep running in a separate terminal)
python tests/test_server.py
```

### Running tests

```bash
# Run isolated sessions (one per challenge, with live output)
python tests/run_isolated.py

# Run via pytest (skips LLM tests by default)
python -m pytest tests/ -v

# Run LLM tests via pytest
python -m pytest tests/ -v --run-llm
```

### Generating reports

After a test run, generate a markdown report from the session logs:

```bash
# Report for specific sessions
python generate_report.py --from session_20260316_223148 --to session_20260316_223956

# Report for all sessions
python generate_report.py
```

The report includes:
- **Per-session table** — challenge, status, tool calls, tokens, cost, time
- **Per-challenge aggregation** — totals across sessions (for multi-session cases)
- **Tool usage breakdown** — which tools were called and how often
- **Session details** — per-session metrics with answers and top tools

## Development

```bash
# Lint
python -m ruff check src/

# Type check
python -m ty check src/

# Tests
python -m pytest
```

## License

MIT
