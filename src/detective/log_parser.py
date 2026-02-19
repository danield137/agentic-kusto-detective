"""Parse JSONL action-log files into session summary dicts."""

import json
from pathlib import Path
from typing import Any


def parse_log_file(path: Path) -> dict[str, Any]:
    """Parse a single JSONL log file and return a session summary dict."""
    events: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    session_id = path.parent.name  # e.g. "session_20260220_210104"
    summary: dict[str, Any] = {
        "session_id": session_id,
        "log_file": str(path),
        "status": "unknown",
        "challenge_url": None,
        "started_at": None,
        "agent_messages": 0,
        "tool_calls": 0,
        "wall_clock_s": None,
        "tool_time_s": None,
        "llm_time_s": None,
    }

    tool_durations: list[float] = []

    for event in events:
        etype = event.get("event")
        if etype == "session_start":
            summary["started_at"] = event.get("timestamp")
            summary["status"] = "running"
        elif etype == "user_prompt":
            prompt = event.get("prompt", "")
            # Extract URL from prompt like "Solve the Kusto Detective challenge at: <url>"
            if "challenge at:" in prompt:
                summary["challenge_url"] = prompt.split("challenge at:")[-1].strip()
            else:
                summary["challenge_url"] = prompt
        elif etype == "agent_message":
            summary["agent_messages"] = event.get("call_number", summary["agent_messages"])
        elif etype == "tool_start":
            summary["tool_calls"] += 1
        elif etype == "tool_end":
            duration = event.get("duration_s", 0.0)
            tool_durations.append(duration)
        elif etype == "session_end":
            summary["status"] = "completed"
            summary["agent_messages"] = event.get("total_agent_calls", summary["agent_messages"])
            summary["wall_clock_s"] = event.get("wall_clock_s")
            summary["tool_time_s"] = event.get("tool_time_s")
            summary["llm_time_s"] = event.get("llm_time_s")

    # Derive stats for incomplete sessions (no session_end event)
    if summary["wall_clock_s"] is None and events:
        last = events[-1]
        summary["wall_clock_s"] = last.get("elapsed_s")
        summary["tool_time_s"] = round(sum(tool_durations), 3)
        if summary["wall_clock_s"] is not None and summary["tool_time_s"] is not None:
            summary["llm_time_s"] = round(summary["wall_clock_s"] - summary["tool_time_s"], 3)
        if summary["status"] == "running":
            summary["status"] = "incomplete"

    return summary


def list_sessions(sessions_dir: Path | str = "sessions") -> list[dict[str, Any]]:
    """List all sessions from the sessions directory, most recent first."""
    base = Path(sessions_dir)
    if not base.exists():
        return []

    sessions = []
    # Each session lives in sessions/<session_id>/session.jsonl
    for session_dir in sorted(base.iterdir(), reverse=True):
        log_file = session_dir / "session.jsonl"
        if session_dir.is_dir() and log_file.exists():
            try:
                sessions.append(parse_log_file(log_file))
            except (json.JSONDecodeError, OSError):
                continue
    return sessions


def generate_worklog(log_path: Path, worklog_path: Path | None = None) -> Path:
    """Generate a formatted markdown worklog from a JSONL action log.

    Returns the path to the written worklog file.
    """
    events: list[dict[str, Any]] = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    session_id = log_path.parent.name
    summary = parse_log_file(log_path)

    # Extract agent messages
    agent_msgs = [e for e in events if e.get("event") == "agent_message"]
    # Last message is typically the agent's own summary
    final_summary = agent_msgs[-1].get("content", "").strip() if agent_msgs else ""

    # Extract tool calls with names and durations
    tool_starts = [e for e in events if e.get("event") == "tool_start"]
    tool_ends = {e["call_id"]: e for e in events if e.get("event") == "tool_end"}
    tool_details: list[str] = []
    for ts in tool_starts:
        cid = ts.get("call_id", "")
        name = ts.get("tool", "?")
        te = tool_ends.get(cid)
        dur = f"{te['duration_s']:.1f}s" if te else "?"
        result_len = te.get("result_length", 0) if te else 0
        tool_details.append(f"| {name} | {dur} | {result_len} chars |")

    # Format timing
    wall = summary.get("wall_clock_s")
    llm = summary.get("llm_time_s")
    tool_t = summary.get("tool_time_s")
    wall_str = f"{wall:.1f}s" if wall else "?"
    llm_str = f"{llm:.1f}s" if llm else "?"
    tool_str = f"{tool_t:.1f}s" if tool_t else "?"

    started = summary.get("started_at", "?")
    status = summary.get("status", "unknown")
    status_emoji = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"

    md = f"""# {status_emoji} Worklog: {session_id}

**Status:** {status}
**Challenge:** {summary.get('challenge_url', '?')}
**Started:** {started}

## Results

{final_summary}

## Stats

| Metric | Value |
|--------|-------|
| Agent messages | {summary.get('agent_messages', '?')} |
| Tool calls | {summary.get('tool_calls', '?')} |
| Wall-clock time | {wall_str} |
| LLM time | {llm_str} |
| Tool time | {tool_str} |

## Tool Calls

| Tool | Duration | Result |
|------|----------|--------|
{chr(10).join(tool_details)}
"""

    if worklog_path is None:
        worklog_path = log_path.parent / "worklog.md"
    worklog_path.write_text(md.strip() + "\n", encoding="utf-8")
    return worklog_path
