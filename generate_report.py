"""Generate a markdown report from session logs.

Parses session.jsonl files to produce a per-challenge breakdown of
metrics including tokens, time, cost, tool calls, and outcome.

Usage:
    python generate_report.py                          # all sessions
    python generate_report.py session_20260316_192530  # specific session
    python generate_report.py session_20260316_1925*   # glob pattern
    python generate_report.py --from session_20260316_192530 --to session_20260316_200000
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"


@dataclass
class SessionMetrics:
    session_id: str
    status: str = "unknown"
    challenge: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    wall_clock_s: float = 0.0
    tool_calls: int = 0
    agent_messages: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    answer: str = ""
    solved: bool = False


def _parse_session(session_dir: Path) -> SessionMetrics | None:
    """Parse a session directory for metrics and challenge info."""
    log_path = session_dir / "session.jsonl"
    if not log_path.exists():
        return None

    m = SessionMetrics(session_id=session_dir.name)

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue

        event = ev.get("event")
        if event == "session_start":
            m.started_at = ev.get("timestamp", "")
        elif event == "session_end":
            m.status = ev.get("status", "unknown")
            m.input_tokens = ev.get("total_input_tokens", 0)
            m.output_tokens = ev.get("total_output_tokens", 0)
            m.cache_read_tokens = ev.get("total_cache_read_tokens", 0)
            m.cost = ev.get("total_cost", 0.0)
            m.wall_clock_s = ev.get("wall_clock_s", 0.0)
            m.tool_calls = ev.get("total_tool_calls", 0)
            m.agent_messages = ev.get("total_agent_calls", 0)
            m.tool_counts = ev.get("tool_counts", {})

    # Identify challenge from challenge.md
    challenge_path = session_dir / "challenge.md"
    if challenge_path.exists():
        content = challenge_path.read_text(encoding="utf-8")
        # Find first case header
        match = re.search(
            r"^##?\s*(?:Challenge|Case)[:\s]*(.+)",
            content, re.IGNORECASE | re.MULTILINE,
        )
        if match:
            m.challenge = match.group(1).strip()

        # Check if solved
        if re.search(r"###?\s*Solution", content, re.IGNORECASE):
            m.solved = True

        # Extract answer
        answer_match = re.search(
            r"\*\*Answer:\*\*\s*(.+?)$",
            content, re.IGNORECASE | re.MULTILINE,
        )
        if answer_match:
            m.answer = answer_match.group(1).strip()

    return m


def _format_time(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f}h"
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    return f"{seconds:.0f}s"


def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def generate_report(
    session_dirs: list[Path],
    title: str = "Agent Session Report",
) -> str:
    """Generate a markdown report from session directories."""
    sessions: list[SessionMetrics] = []
    for d in sorted(session_dirs):
        m = _parse_session(d)
        if m:
            sessions.append(m)

    if not sessions:
        return f"# {title}\n\nNo sessions found.\n"

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Sessions:** {len(sessions)}")

    # Totals
    total_input = sum(s.input_tokens for s in sessions)
    total_output = sum(s.output_tokens for s in sessions)
    total_cached = sum(s.cache_read_tokens for s in sessions)
    total_cost = sum(s.cost for s in sessions)
    total_time = sum(s.wall_clock_s for s in sessions)
    total_tools = sum(s.tool_calls for s in sessions)
    solved_count = sum(1 for s in sessions if s.solved)

    lines.append(f"**Solved:** {solved_count}/{len(sessions)}")
    lines.append(f"**Total time:** {_format_time(total_time)}")
    total_tok = total_input + total_output
    lines.append(f"**Total tokens:** {_format_tokens(total_tok)} "
                 f"(in: {_format_tokens(total_input)}, "
                 f"out: {_format_tokens(total_output)}, "
                 f"cached: {_format_tokens(total_cached)})")
    lines.append(f"**Total cost:** ${total_cost:.4f}")
    lines.append(f"**Total tool calls:** {total_tools}")
    lines.append("")

    # Per-session table
    lines.append("## Per-Session Breakdown")
    lines.append("")
    lines.append("| # | Session | Challenge | Status | Tools | Tokens | Cost | Time |")
    lines.append("|---|---------|-----------|--------|-------|--------|------|------|")

    for i, s in enumerate(sessions, 1):
        status = "✅" if s.solved else ("⏱️" if s.status == "step_limit" else "❌")
        tok = s.input_tokens + s.output_tokens
        challenge = s.challenge[:40] if s.challenge else "(unknown)"
        lines.append(
            f"| {i} | `{s.session_id}` | {challenge} | {status} {s.status} "
            f"| {s.tool_calls} | {_format_tokens(tok)} | ${s.cost:.4f} "
            f"| {_format_time(s.wall_clock_s)} |"
        )

    lines.append("")

    # Per-challenge aggregation
    by_challenge: dict[str, list[SessionMetrics]] = {}
    for s in sessions:
        key = s.challenge or "(unknown)"
        by_challenge.setdefault(key, []).append(s)

    if len(by_challenge) > 1 or (len(by_challenge) == 1 and len(sessions) > 1):
        lines.append("## Per-Challenge Aggregation")
        lines.append("")
        lines.append("| Challenge | Sessions | Status | Tools | Tokens | Cost | Time | Answer |")
        lines.append("|-----------|----------|--------|-------|--------|------|------|--------|")

        for challenge, challenge_sessions in sorted(by_challenge.items()):
            n = len(challenge_sessions)
            tok = sum(s.input_tokens + s.output_tokens for s in challenge_sessions)
            cost = sum(s.cost for s in challenge_sessions)
            wall = sum(s.wall_clock_s for s in challenge_sessions)
            tools = sum(s.tool_calls for s in challenge_sessions)
            any_solved = any(s.solved for s in challenge_sessions)
            status = "✅" if any_solved else "🔄"
            answer = next((s.answer for s in challenge_sessions if s.answer), "—")
            lines.append(
                f"| {challenge[:40]} | {n} | {status} "
                f"| {tools} | {_format_tokens(tok)} | ${cost:.4f} "
                f"| {_format_time(wall)} | {answer} |"
            )

        lines.append("")

    # Tool usage breakdown
    all_tools: dict[str, int] = {}
    for s in sessions:
        for tool, count in s.tool_counts.items():
            all_tools[tool] = all_tools.get(tool, 0) + count

    if all_tools:
        lines.append("## Tool Usage")
        lines.append("")
        lines.append("| Tool | Calls |")
        lines.append("|------|-------|")
        for tool, count in sorted(all_tools.items(), key=lambda x: -x[1]):
            lines.append(f"| {tool} | {count} |")
        lines.append("")

    # Detailed per-session sections
    lines.append("## Session Details")
    lines.append("")

    for s in sessions:
        status_icon = "✅" if s.solved else "❌"
        lines.append(f"### {status_icon} {s.session_id}")
        lines.append("")
        if s.challenge:
            lines.append(f"- **Challenge:** {s.challenge}")
        lines.append(f"- **Status:** {s.status}")
        if s.answer:
            lines.append(f"- **Answer:** {s.answer}")
        tok = s.input_tokens + s.output_tokens
        lines.append(f"- **Tokens:** {_format_tokens(tok)} "
                     f"(in: {_format_tokens(s.input_tokens)}, "
                     f"out: {_format_tokens(s.output_tokens)}, "
                     f"cached: {_format_tokens(s.cache_read_tokens)})")
        lines.append(f"- **Cost:** ${s.cost:.4f}")
        lines.append(f"- **Time:** {_format_time(s.wall_clock_s)}")
        lines.append(f"- **Tool calls:** {s.tool_calls}")
        lines.append(f"- **Agent messages:** {s.agent_messages}")
        if s.tool_counts:
            top_tools = sorted(s.tool_counts.items(), key=lambda x: -x[1])[:5]
            tools_str = ", ".join(f"{t}: {c}" for t, c in top_tools)
            lines.append(f"- **Top tools:** {tools_str}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    from_id = ""
    to_id = ""

    # Parse --from / --to
    if "--from" in args:
        idx = args.index("--from")
        from_id = args[idx + 1]
        args = args[:idx] + args[idx + 2:]
    if "--to" in args:
        idx = args.index("--to")
        to_id = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    # Collect session directories
    all_sessions = sorted(
        d for d in SESSIONS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("session_")
    )

    if from_id or to_id:
        filtered = []
        for d in all_sessions:
            if from_id and d.name < from_id:
                continue
            if to_id and d.name > to_id:
                continue
            filtered.append(d)
        session_dirs = filtered
    elif args:
        # Specific session IDs or glob patterns
        import fnmatch
        session_dirs = []
        for pattern in args:
            for d in all_sessions:
                if fnmatch.fnmatch(d.name, pattern) or d.name == pattern:
                    if d not in session_dirs:
                        session_dirs.append(d)
    else:
        session_dirs = all_sessions

    if not session_dirs:
        print("No matching sessions found.", file=sys.stderr)
        sys.exit(1)

    report = generate_report(session_dirs)
    print(report)


if __name__ == "__main__":
    main()
