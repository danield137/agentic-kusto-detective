# Implementation Plan — Agentic Kusto Detective

## Problem Statement

Build a lab and benchmark that lets AI agents autonomously solve [Kusto Detective Agency](https://detective.kusto.io/) Season 1 challenges. Agents are scored on LLM call count and token usage. The system should support pluggable agent configurations and eventually host a public scoreboard.

## Key Design Decisions

- **Agent framework:** Copilot SDK (Python) with Claude Opus 4.6
- **Auth:** Local Azure identity (signed-in user) for Kusto access
- **Kusto cluster:** `https://danieldror2.swedencentral.dev.kusto.windows.net/` (Sandbox db)
- **Scoreboard:** FastAPI + simple frontend web app
- **Agent configs:** System prompt, skills, MCP tools, knowledge base (markdown) — all pluggable
- **Anti-cheat:** Small LLM verifies submissions aren't hardcoded answers
- **Memory:** Season 1 cases are interlinked; agent memory/learnings must carry over between cases

### Agent Toolbelt

The agent is a multi-tool autonomous actor. It needs **hands and eyes**:

| Tool | Purpose | Implementation |
|------|---------|----------------|
| **Browser (Playwright)** | Read challenge descriptions from detective.kusto.io, submit answers, verify results | Baseline: Playwright Python API directly. Pluggable path: Playwright MCP server |
| **Kusto client** | Execute KQL queries and management commands against challenge clusters | azure-kusto-data with DefaultAzureCredential |
| **Shell** | Run local commands (data processing, scripting, etc.) | subprocess / tool wrapper |
| **Filesystem** | Read/write scratch files, store intermediate results | local disk access via tool wrapper |

### Action Logging

Every agent interaction is logged to `sessions/session_*/session.jsonl` with full fidelity — all inputs and outputs. This is the source of truth for:
- Scoring (call count, token usage)
- Debugging agent behavior (`--follow` mode for live streaming)
- Anti-cheat verification
- Replay and analysis

### Sandboxing

- **Now:** No guard rails, runs locally
- **Future:** AKS-based isolation for untrusted agent configs in the scoreboard pipeline

---

## Milestone 0 — Vanilla POC ✅

Get a single Kusto Detective case solved with the simplest possible setup.

**Status:** Complete. Agent solved the onboarding challenge end-to-end.

**Delivered:**
- Copilot SDK agent with Claude Opus 4.6, 7 tools (Kusto + Playwright browser)
- Action logging to JSON-lines (tool calls, durations, agent messages)
- `--follow` mode for live streaming of agent thinking and tool calls
- `DETECTIVE_CLUSTER_URI` env var for site login

---

## Milestone 1 — Foundation & Formalized Tooling

Take the vanilla POC and formalize it: proper project structure, all four tools, action logging, and reproducible E2E sessions.

- **project-scaffolding**: Formalize Python project structure (uv, src layout)
- **action-log**: Token count tracking (input/output per LLM call)
- **shell-tool**: Shell execution tool — run commands, capture stdout/stderr, configurable timeout
- **filesystem-tool**: File read/write tool — scoped to a per-session scratch directory
- **challenge-model**: Data model for a challenge (URL, cluster URI, database, problem statement)
- **single-case-session**: Agent with all four tools + action logger
- **e2e-validation**: Reproducible E2E run with structured pass/fail output

---

## Milestone 2 — Season 1 Runner & Memory

All Season 1 cases running sequentially with memory carry-over and structured results.

- **challenge-catalog**: Crawl detective.kusto.io Season 1, catalog all cases
- **runner-harness**: Sequential runner feeding cases to agent, collecting results
- **memory-system**: Persistent memory between cases (schema discoveries, KQL patterns, solutions)
- **answer-verification**: Browser-based submission and verification capture
- **results-output**: Structured run report (per-case pass/fail, calls, tokens, time, queries)
- **baseline-run**: Full Season 1 run, establish reference score

---

## Milestone 3 — Agent Configurability

Make the agent setup pluggable so different configurations can compete.

- **config-schema**: Schema for agent configs (system prompt, skills, MCP tools, knowledge base)
- **config-loader**: Assemble agent from config file
- **mcp-tool-bridge**: Generic MCP tool adapter for any MCP server
- **skills-framework**: Reusable KQL strategies/patterns as equippable skills
- **knowledge-base**: Inject markdown knowledge bases into agent context
- **config-validation**: Validate configs before running
- **config-comparison**: Run Season 1 with multiple configs, produce comparison report

---

## Milestone 4 — Scoreboard & Anti-Cheat

Public-facing scoreboard web app with submission pipeline.

- **score-model**: Composite score from LLM call count + token usage, configurable weights
- **results-db**: Persistent storage (SQLite)
- **fastapi-backend**: Submit config, trigger run, leaderboard, run details, download action log
- **submission-pipeline**: Accept config uploads, validate, run, store results
- **anti-cheat**: LLM-based detection of hardcoded answers or trivial bypasses
- **frontend**: Leaderboard, run detail view, action log explorer, config diff
- **deployment**: Containerize (Docker). Future: AKS for sandboxed untrusted configs

---

## Dependencies

```
Milestone 0 → Milestone 1 (vanilla POC proves feasibility, then formalize)
Milestone 1 → Milestone 2 (need single-case working before full season)
Milestone 2 → Milestone 3 (need runner before making it configurable)
Milestone 3 → Milestone 4 (need pluggable configs before accepting submissions)
```

## Open Questions

- How many cases are in Season 1? Need to crawl detective.kusto.io to catalog them
- Scoring formula weights: equal call count vs. token usage, or favor one?
- Should action logs include full Kusto result sets, or just metadata (row count, schema)?
