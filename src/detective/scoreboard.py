"""Scoreboard — post-hoc collector that builds per-case metrics from session logs.

Scans all session directories, parses session.jsonl for metrics and
challenge.md for case identification, then aggregates per-case across
sessions into scoreboard.json.

Usage:
    python -m detective.scoreboard           # collect and print
    python -m detective.scoreboard --json    # collect and write scoreboard.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parents[2] / "sessions"
SCOREBOARD_PATH = Path(__file__).resolve().parents[2] / "scoreboard.json"


@dataclass
class SessionMetrics:
    """Metrics extracted from a single session's JSONL log."""

    session_id: str
    status: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    wall_clock_s: float = 0.0
    tool_calls: int = 0
    ended_at: str = ""


@dataclass
class CaseEntry:
    """Accumulated metrics for a single case across sessions."""

    name: str
    status: str = "in_progress"
    answer: str = ""
    solution_summary: str = ""
    sessions: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    wall_clock_s: float = 0.0
    tool_calls: int = 0
    solved_at: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "name": self.name,
            "status": self.status,
            "sessions": self.sessions,
            "tokens": {
                "input": self.input_tokens,
                "output": self.output_tokens,
                "cached": self.cache_read_tokens,
            },
            "cost": round(self.cost, 6),
            "wall_clock_s": round(self.wall_clock_s, 1),
            "tool_calls": self.tool_calls,
        }
        if self.answer:
            d["answer"] = self.answer
        if self.solution_summary:
            d["solution_summary"] = self.solution_summary
        if self.solved_at:
            d["solved_at"] = self.solved_at
        return d


def _parse_session_metrics(session_dir: Path) -> SessionMetrics | None:
    """Parse session.jsonl for the session_end event metrics."""
    log_path = session_dir / "session.jsonl"
    if not log_path.exists():
        return None
    session_id = session_dir.name
    metrics = SessionMetrics(session_id=session_id)
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("event") == "session_end":
            metrics.status = ev.get("status", "unknown")
            metrics.input_tokens = ev.get("total_input_tokens", 0)
            metrics.output_tokens = ev.get("total_output_tokens", 0)
            metrics.cache_read_tokens = ev.get("total_cache_read_tokens", 0)
            metrics.cost = ev.get("total_cost", 0.0)
            metrics.wall_clock_s = ev.get("wall_clock_s", 0.0)
            metrics.tool_calls = ev.get("total_tool_calls", 0)
            metrics.ended_at = ev.get("timestamp", "")
    return metrics


# Patterns for case identification in challenge.md
_CASE_HEADER_RE = re.compile(
    r"^##?\s*(?:Case|Challenge)[:\s]*(.+)",
    re.IGNORECASE | re.MULTILINE,
)
_SOLUTION_RE = re.compile(
    r"^###?\s*Solution.*?\n\*\*Answer:\*\*\s*(.+?)$",
    re.IGNORECASE | re.MULTILINE,
)
_SOLUTION_HOW_RE = re.compile(
    r"\*\*How:\*\*\s*(.+?)(?:\n###|\n##|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def _slugify(name: str) -> str:
    """Convert a case name to a URL-friendly slug."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")


def _identify_cases(session_dir: Path) -> list[dict]:
    """Identify case(s) from challenge.md in a session directory.

    Returns a list of dicts with keys: name, slug, answer, solution_summary.
    Most sessions have exactly one case.
    """
    challenge_path = session_dir / "challenge.md"
    if not challenge_path.exists():
        return []

    content = challenge_path.read_text(encoding="utf-8")
    cases: list[dict] = []

    # Find all case headers
    headers = list(_CASE_HEADER_RE.finditer(content))
    if not headers:
        # Fallback: try the first markdown heading
        first_heading = re.match(r"^#\s+(.+)", content)
        if first_heading:
            name = first_heading.group(1).strip()
            cases.append({"name": name, "slug": _slugify(name)})

    for i, match in enumerate(headers):
        name = match.group(1).strip()
        # Get the section content (up to next case header or end)
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        section = content[start:end]

        case_info: dict = {"name": name, "slug": _slugify(name)}

        # Look for solution answer
        sol_match = _SOLUTION_RE.search(section)
        if sol_match:
            case_info["answer"] = sol_match.group(1).strip()

        # Look for solution explanation
        how_match = _SOLUTION_HOW_RE.search(section)
        if how_match:
            case_info["solution_summary"] = how_match.group(1).strip()

        cases.append(case_info)

    return cases


def collect(sessions_dir: Path = SESSIONS_DIR) -> dict:
    """Scan all session directories and build a scoreboard.

    Returns the scoreboard dict ready to write to JSON.
    """
    cases: dict[str, CaseEntry] = {}

    session_dirs = sorted(
        (d for d in sessions_dir.iterdir()
         if d.is_dir() and d.name.startswith("session_")),
    )

    for session_dir in session_dirs:
        metrics = _parse_session_metrics(session_dir)
        if metrics is None:
            continue

        identified = _identify_cases(session_dir)
        if not identified:
            continue

        # Attribute session metrics to identified case(s)
        # If multiple cases in one session, split evenly (best we can do post-hoc)
        n = len(identified)
        for case_info in identified:
            slug = case_info["slug"]
            if slug not in cases:
                cases[slug] = CaseEntry(name=case_info["name"])

            entry = cases[slug]
            if metrics.session_id not in entry.sessions:
                entry.sessions.append(metrics.session_id)
                entry.input_tokens += metrics.input_tokens // n
                entry.output_tokens += metrics.output_tokens // n
                entry.cache_read_tokens += metrics.cache_read_tokens // n
                entry.cost += metrics.cost / n
                entry.wall_clock_s += metrics.wall_clock_s / n
                entry.tool_calls += metrics.tool_calls // n

            # Update answer/solution if found
            if case_info.get("answer"):
                entry.answer = case_info["answer"]
                entry.status = "solved"
                if not entry.solved_at and metrics.ended_at:
                    entry.solved_at = metrics.ended_at
            if case_info.get("solution_summary"):
                entry.solution_summary = case_info["solution_summary"]

    # Build scoreboard
    total_input = sum(c.input_tokens for c in cases.values())
    total_output = sum(c.output_tokens for c in cases.values())
    total_cached = sum(c.cache_read_tokens for c in cases.values())
    total_cost = sum(c.cost for c in cases.values())
    solved = sum(1 for c in cases.values() if c.status == "solved")

    scoreboard = {
        "season_1": {
            "cases": {slug: entry.to_dict() for slug, entry in sorted(cases.items())},
            "totals": {
                "cases_solved": solved,
                "cases_total": len(cases),
                "tokens": {
                    "input": total_input,
                    "output": total_output,
                    "cached": total_cached,
                },
                "cost": round(total_cost, 6),
            },
        },
    }
    return scoreboard


def print_scoreboard(scoreboard: dict) -> None:
    """Print a human-readable scoreboard summary."""
    s1 = scoreboard.get("season_1", {})
    totals = s1.get("totals", {})
    cases = s1.get("cases", {})

    print(f"\n{'=' * 70}")
    print(f"  Season 1 Scoreboard — {totals.get('cases_solved', 0)}"
          f"/{totals.get('cases_total', 0)} cases solved")
    print(f"{'=' * 70}")

    tokens = totals.get("tokens", {})
    total_tok = tokens.get("input", 0) + tokens.get("output", 0)
    print(f"  Total tokens: {total_tok:,} "
          f"(in: {tokens.get('input', 0):,}, "
          f"out: {tokens.get('output', 0):,}, "
          f"cached: {tokens.get('cached', 0):,})")
    print(f"  Total cost:   ${totals.get('cost', 0):.4f}")
    print()

    if not cases:
        print("  No cases found. Run sessions first, or check that sessions/ has data.")
        print(f"{'=' * 70}\n")
        return

    # Per-case table
    print(f"  {'Case':<35} {'Status':<10} {'Sessions':>8} "
          f"{'Tokens':>10} {'Cost':>8} {'Time':>8}")
    print(f"  {'-' * 35} {'-' * 10} {'-' * 8} {'-' * 10} {'-' * 8} {'-' * 8}")

    for slug, case in cases.items():
        tok = case.get("tokens", {})
        total = tok.get("input", 0) + tok.get("output", 0)
        status = "✅" if case.get("status") == "solved" else "🔄"
        wall = case.get("wall_clock_s", 0)
        time_str = f"{wall / 60:.0f}m" if wall > 60 else f"{wall:.0f}s"
        print(f"  {case.get('name', slug):<35} {status:<10} "
              f"{len(case.get('sessions', [])):>8} "
              f"{total:>10,} ${case.get('cost', 0):>7.4f} {time_str:>8}")

    print(f"{'=' * 70}\n")


def main() -> None:
    write_json = "--json" in sys.argv

    scoreboard = collect()
    print_scoreboard(scoreboard)

    if write_json:
        SCOREBOARD_PATH.write_text(
            json.dumps(scoreboard, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Written to {SCOREBOARD_PATH}")


if __name__ == "__main__":
    main()
