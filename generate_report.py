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
class CaseMetrics:
    """Per-case metrics extracted from JSONL event segmentation."""

    case_number: int
    name: str = ""
    solved: bool = False
    answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost: float = 0.0
    wall_clock_s: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0


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
    cases: list[CaseMetrics] = field(default_factory=list)


def _analyze_per_case(session_dir: Path) -> list[CaseMetrics]:
    """Segment JSONL events by case and compute per-case metrics.

    Handles multi-session JSONLs (run + resume) by chaining
    elapsed times without inter-session gaps.
    """
    log_path = session_dir / "session.jsonl"
    if not log_path.exists():
        return []

    events: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not events:
        return []

    # Split into sub-sessions (resume appends to same JSONL)
    sub_sessions: list[list[dict]] = []
    current: list[dict] = []
    for ev in events:
        if ev.get("event") == "session_start" and current:
            sub_sessions.append(current)
            current = []
        current.append(ev)
    if current:
        sub_sessions.append(current)

    # Build global timeline: chain sub-session elapsed times
    global_events: list[dict] = []
    offset = 0.0
    for idx, sess_events in enumerate(sub_sessions):
        if idx > 0:
            prev_last = sub_sessions[idx - 1][-1]
            offset += prev_last.get("elapsed_s", 0)
        for ev in sess_events:
            ev["_ge"] = offset + ev.get("elapsed_s", 0)
            global_events.append(ev)

    # Detect case boundaries from agent messages and file creation
    case_starts: dict[int, float] = {}
    for ev in global_events:
        args_str = str(ev.get("args", {}).get("arguments", ""))
        content = ev.get("content", "")
        elapsed = ev["_ge"]
        etype = ev.get("event", "")

        if etype == "agent_message":
            for m in re.finditer(r"Case (\d+)", content):
                cn = int(m.group(1))
                low = content.lower()
                kws = ["click", "start", "let me", "move on",
                       "continue"]
                if any(kw in low for kw in kws):
                    if cn not in case_starts or elapsed < case_starts[cn]:
                        case_starts[cn] = elapsed
                    break

        if etype == "tool_start" and ev.get("tool") == "create":
            # New naming: challenge_C_case_N.md
            m = re.search(r"challenge_\d+_case_(\d+)\.md", args_str)
            if not m:
                # Legacy: challenge_N.md
                m = re.search(r"challenge_(\d+)\.md", args_str)
            if m:
                cn = int(m.group(1))
                if cn not in case_starts or elapsed < case_starts[cn]:
                    case_starts[cn] = elapsed

    if not case_starts:
        return []

    sorted_cases = sorted(case_starts.items())

    def _get_case(elapsed: float) -> int:
        case = 0
        for cn, start in sorted_cases:
            if elapsed >= start:
                case = cn
        return case

    # Aggregate metrics per case
    buckets: dict[int, dict] = {}
    for ev in global_events:
        elapsed = ev["_ge"]
        cn = _get_case(elapsed)
        b = buckets.setdefault(cn, {
            "input": 0, "output": 0, "cached": 0, "cost": 0.0,
            "llm_calls": 0, "tools": 0,
            "first_t": elapsed, "last_t": elapsed,
        })
        b["last_t"] = max(b["last_t"], elapsed)

        if ev.get("event") == "usage":
            b["input"] += ev.get("input_tokens", 0)
            b["output"] += ev.get("output_tokens", 0)
            b["cached"] += ev.get("cache_read_tokens", 0)
            b["cost"] += ev.get("cost", 0)
            b["llm_calls"] += 1
        elif ev.get("event") == "tool_start":
            b["tools"] += 1

    # Build CaseMetrics list (skip case 0 = setup/nav)
    results: list[CaseMetrics] = []
    for cn in sorted(buckets):
        if cn == 0:
            continue  # setup/nav, not a real case
        b = buckets[cn]
        cm = CaseMetrics(
            case_number=cn,
            input_tokens=b["input"],
            output_tokens=b["output"],
            cache_read_tokens=b["cached"],
            cost=b["cost"],
            wall_clock_s=b["last_t"] - b["first_t"],
            llm_calls=b["llm_calls"],
            tool_calls=b["tools"],
        )
        # Enrich from challenge file (try new naming first)
        cf_matches = list(session_dir.glob(f"challenge_*_case_{cn}.md"))
        cf = cf_matches[0] if cf_matches else session_dir / f"challenge_{cn}.md"
        if cf.exists():
            content = cf.read_text(encoding="utf-8")
            heading = re.sub(
                r"^#\s*(Challenge:\s*)?", "",
                content.split("\n")[0],
            ).strip()
            cm.name = heading
            cm.solved = bool(
                re.search(r"###?\s*Solution", content, re.IGNORECASE)
            )
            ans = re.search(
                r"\*\*Answer:\*\*\s*(.+?)$",
                content, re.IGNORECASE | re.MULTILINE,
            )
            if ans:
                cm.answer = ans.group(1).strip()
        results.append(cm)

    return results


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

    # Per-case analysis from JSONL event segmentation
    m.cases = _analyze_per_case(session_dir)

    # Derive session-level challenge info from per-case analysis
    # (seeded challenge files would mislead — use active cases only)
    if m.cases:
        # The session's primary challenge is the highest case worked on
        active = m.cases[-1]
        m.challenge = active.name or f"Case {active.case_number}"
        m.solved = all(c.solved for c in m.cases)
        m.answer = active.answer
    else:
        # Fallback: scan challenge files (legacy / no JSONL segmentation)
        challenge_files = sorted(session_dir.glob("challenge_*.md"))
        legacy = session_dir / "challenge.md"
        if not challenge_files and legacy.exists():
            challenge_files = [legacy]

        for challenge_path in challenge_files:
            content = challenge_path.read_text(encoding="utf-8")
            match = re.search(
                r"^##?\s*(?:Challenge|Case)[:\s]*(.+)",
                content, re.IGNORECASE | re.MULTILINE,
            )
            if match and not m.challenge:
                m.challenge = match.group(1).strip()
            if re.search(r"###?\s*Solution", content, re.IGNORECASE):
                m.solved = True
            answer_match = re.search(
                r"\*\*Answer:\*\*\s*(.+?)$",
                content, re.IGNORECASE | re.MULTILINE,
            )
            if answer_match and not m.answer:
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

    # Per-case breakdown (from JSONL segmentation)
    all_cases: list[tuple[str, CaseMetrics]] = []
    for s in sessions:
        for c in s.cases:
            all_cases.append((s.session_id, c))

    if all_cases:
        lines.append("## Per-Case Breakdown")
        lines.append("")
        lines.append(
            "| Case | Session | Status | LLM | Tools "
            "| Input | Output | Cached | Cost | Time | Answer |"
        )
        lines.append(
            "|------|---------|--------|-----|-------"
            "|-------|--------|--------|------|------|--------|"
        )

        for sid, c in all_cases:
            status = "✅" if c.solved else "🔄"
            name = c.name[:30] if c.name else f"Case {c.case_number}"
            answer = c.answer[:20] if c.answer else "—"
            lines.append(
                f"| {name} | `{sid[-15:]}` "
                f"| {status} | {c.llm_calls} | {c.tool_calls} "
                f"| {_format_tokens(c.input_tokens)} "
                f"| {_format_tokens(c.output_tokens)} "
                f"| {_format_tokens(c.cache_read_tokens)} "
                f"| ${c.cost:.4f} "
                f"| {_format_time(c.wall_clock_s)} "
                f"| {answer} |"
            )

        # Per-case totals
        tc_input = sum(c.input_tokens for _, c in all_cases)
        tc_output = sum(c.output_tokens for _, c in all_cases)
        tc_cached = sum(c.cache_read_tokens for _, c in all_cases)
        tc_cost = sum(c.cost for _, c in all_cases)
        tc_llm = sum(c.llm_calls for _, c in all_cases)
        tc_tools = sum(c.tool_calls for _, c in all_cases)
        tc_wall = sum(c.wall_clock_s for _, c in all_cases)
        tc_solved = sum(1 for _, c in all_cases if c.solved)
        lines.append(
            f"| **Total ({tc_solved}/{len(all_cases)} solved)** | "
            f"| | {tc_llm} | {tc_tools} "
            f"| {_format_tokens(tc_input)} "
            f"| {_format_tokens(tc_output)} "
            f"| {_format_tokens(tc_cached)} "
            f"| ${tc_cost:.4f} "
            f"| {_format_time(tc_wall)} | |"
        )

        lines.append("")

        # Cache efficiency
        if tc_input > 0:
            cache_rate = tc_cached / tc_input * 100
            fresh = tc_input - tc_cached
            lines.append(
                f"**Cache hit rate:** {cache_rate:.1f}% — "
                f"{_format_tokens(tc_cached)} cached, "
                f"{_format_tokens(fresh)} fresh input"
            )
            lines.append("")

    # Per-challenge aggregation (group per-case data by case name)
    by_case_name: dict[str, list[CaseMetrics]] = {}
    for _, c in all_cases:
        key = c.name or f"Case {c.case_number}"
        by_case_name.setdefault(key, []).append(c)

    if by_case_name:
        lines.append("## Per-Challenge Aggregation")
        lines.append("")
        lines.append(
            "| Challenge | Attempts | Status "
            "| LLM | Tools | Input | Output "
            "| Cost | Time | Answer |"
        )
        lines.append(
            "|-----------|----------|--------"
            "|-----|-------|-------|--------"
            "|------|------|--------|"
        )

        for name, case_list in sorted(by_case_name.items()):
            n = len(case_list)
            llm = sum(c.llm_calls for c in case_list)
            tools = sum(c.tool_calls for c in case_list)
            inp = sum(c.input_tokens for c in case_list)
            out = sum(c.output_tokens for c in case_list)
            cost = sum(c.cost for c in case_list)
            wall = sum(c.wall_clock_s for c in case_list)
            any_solved = any(c.solved for c in case_list)
            status = "✅" if any_solved else "🔄"
            answer = next(
                (c.answer[:20] for c in case_list if c.answer), "—",
            )
            lines.append(
                f"| {name[:35]} | {n} | {status} "
                f"| {llm} | {tools} "
                f"| {_format_tokens(inp)} "
                f"| {_format_tokens(out)} "
                f"| ${cost:.4f} "
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

        if s.cases:
            lines.append("")
            lines.append(
                "| Case | Status | LLM | Tools "
                "| Input | Output | Cached | Time |"
            )
            lines.append(
                "|------|--------|-----|-------"
                "|-------|--------|--------|------|"
            )
            for c in s.cases:
                st = "✅" if c.solved else "🔄"
                nm = c.name[:28] if c.name else f"Case {c.case_number}"
                lines.append(
                    f"| {nm} | {st} "
                    f"| {c.llm_calls} | {c.tool_calls} "
                    f"| {_format_tokens(c.input_tokens)} "
                    f"| {_format_tokens(c.output_tokens)} "
                    f"| {_format_tokens(c.cache_read_tokens)} "
                    f"| {_format_time(c.wall_clock_s)} |"
                )

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
