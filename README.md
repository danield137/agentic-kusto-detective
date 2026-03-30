# Agentic Kusto Detective

AI agent that solves [Kusto Detective Agency](https://detective.kusto.io/) challenges autonomously — reads challenge pages via browser, queries data with KQL, reasons through puzzles, and submits answers.

Built with [GitHub Copilot SDK](https://github.com/github/copilot-sdk) + Claude Opus 4.6 (1M context) + GPT-5.4.

| Season | Status | Cases | Model(s) | Report |
|--------|--------|-------|----------|--------|
| 1 — Echoes of Deception | ✅ Complete | 10/10 | Opus 4.6 1M | [Report](solved_challenges/1/report.md) |
| 2 — New Shadows Over Digitown | ✅ Complete | 5/5 | Opus 4.6 1M | [Report](solved_challenges/2/report.md) |
| 3 — Call of the Cyber Duty | ✅ Complete | 10/10 | Opus 4.6 1M + GPT-5.4 | [Report](solved_challenges/3/report.md) |

## Quick Start

```bash
pip install -e ".[dev]"
playwright install chromium
```

Set environment variables:
```bash
export GITHUB_TOKEN=<your-github-pat>
export DETECTIVE_CLUSTER_URI=<your-free-kusto-cluster-uri>
```

Azure auth uses `DefaultAzureCredential` — run `az login` first.

```bash
# Solve challenge 1, case by case
python run.py ralph --challenge-num 1 -i 10

# Single iteration
python run.py ralph --challenge-num 1 -i 1

# Resume from a prior session
python run.py ralph --seed <session_id> -i 5

# Resume an interrupted session (exact conversation)
python run.py resume <session_id>

# See all options
python run.py --help
```

Each iteration starts a fresh session seeded from the last. The agent works one case per iteration, saves findings, and stops. Next iteration picks up the next unsolved case.

## How It Works

```
run.py ralph --challenge-num 1
  → creates session, loads bundle (prompt + tools + skills)
  → agent logs into detective.kusto.io via Playwright
  → reads challenge, explores DB with KQL, reasons, submits answer
  → saves memory + case file for next iteration
```

**Tools:** KQL queries, Playwright browser, persistent memory, reasoning tree, handoff context, expert consultation (second LLM).

**Bundles:** Declarative agent configs under `agents/bundles/`. Each has a prompt template, skills, knowledge files, and MCP server configs.

**Sessions:** Every run produces `sessions/session_<timestamp>/` with full action logs (JSONL), case files, memory, and reasoning state.

## Project Layout

```
run.py                   # CLI entry point — ralph loop + resume
agents/bundles/          # Agent configurations (prompt, skills, knowledge)
src/detective/           # Core: tools, logging, session management
solved_challenges/       # Reports for completed challenges
generate_report.py       # Generate markdown reports from session logs
```

## Development

```bash
ruff check src/          # Lint
pytest tests/ -v         # Test (add --run-llm for LLM tests)
```

## License

MIT
