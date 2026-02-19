"""Action logger — records every agent↔tool interaction to a JSON-lines file."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path


class ActionLog:
    """Writes structured action log entries to a .jsonl file."""

    def __init__(self, log_path: Path, follow: bool = False, model: str = ""):
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = log_path
        self._start_time = time.monotonic()
        self._call_count = 0
        self._tool_count = 0
        self._tool_time = 0.0  # cumulative tool execution time (seconds)
        self._pending_tools: dict[str, dict] = {}
        self._follow = follow
        self._model = model
        self._task = ""  # initial prompt/task
        self._tool_counts: dict[str, int] = {}  # per-tool-name counts
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cache_read_tokens = 0
        self._total_cost = 0.0
        self._status = "running"

        self._write({"event": "session_start", "log_file": str(self._path), "model": model})

    @property
    def path(self) -> Path:
        return self._path

    @property
    def call_count(self) -> int:
        return self._call_count

    def _write(self, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        entry["elapsed_s"] = round(time.monotonic() - self._start_time, 3)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log_prompt(self, prompt: str) -> None:
        if not self._task:
            self._task = prompt
        self._write({"event": "user_prompt", "prompt": prompt})

    def log_agent_message(self, content: str) -> None:
        self._call_count += 1
        self._write(
            {
                "event": "agent_message",
                "content": content[:2000],
                "call_number": self._call_count,
            }
        )

    def log_tool_start(self, tool_name: str, args: dict) -> str:
        """Log tool invocation start. Returns a call_id for pairing with tool_end."""
        self._tool_count += 1
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1
        call_id = f"{tool_name}_{time.monotonic_ns()}"
        self._pending_tools[call_id] = {"start": time.monotonic()}
        self._write(
            {
                "event": "tool_start",
                "call_id": call_id,
                "tool": tool_name,
                "args": _truncate_args(args),
            }
        )
        if self._follow:
            elapsed = round(time.monotonic() - self._start_time, 1)
            _fprint(f"  🔧 [{elapsed}s] tool #{self._tool_count}: {tool_name}")
            for k, v in _truncate_args(args).items():
                preview = str(v).replace("\n", "\\n")[:120]
                _fprint(f"       {k}: {preview}")
        return call_id

    def log_tool_end(self, call_id: str, tool_name: str, result: str) -> None:
        duration = 0.0
        if call_id in self._pending_tools:
            duration = time.monotonic() - self._pending_tools.pop(call_id)["start"]
        self._tool_time += duration
        self._write(
            {
                "event": "tool_end",
                "call_id": call_id,
                "tool": tool_name,
                "result_length": len(result),
                "result_preview": result[:500],
                "duration_s": round(duration, 3),
            }
        )
        if self._follow:
            preview = result.replace("\n", "\\n")[:200]
            _fprint(f"  ✅  → {tool_name} ({duration:.1f}s, {len(result)} chars)")
            _fprint(f"       {preview}")

    def log_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cost: float = 0.0,
        model: str = "",
    ) -> None:
        """Log an LLM usage event (emitted by the SDK after each API call)."""
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cache_read_tokens += cache_read_tokens
        self._total_cost += cost
        self._write(
            {
                "event": "usage",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cost": cost,
                "model": model,
            }
        )

    def log_session_end(self) -> None:
        elapsed = time.monotonic() - self._start_time
        llm_time = elapsed - self._tool_time
        self._write(
            {
                "event": "session_end",
                "model": self._model,
                "status": self._status,
                "total_agent_calls": self._call_count,
                "total_tool_calls": self._tool_count,
                "tool_counts": self._tool_counts,
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "total_cache_read_tokens": self._total_cache_read_tokens,
                "total_cost": round(self._total_cost, 6),
                "wall_clock_s": round(elapsed, 3),
                "tool_time_s": round(self._tool_time, 3),
                "llm_time_s": round(llm_time, 3),
            }
        )

    def print_summary(self) -> None:
        elapsed = round(time.monotonic() - self._start_time, 1)
        tool_time = round(self._tool_time, 1)
        llm_time = round(elapsed - self._tool_time, 1)
        total_tokens = self._total_input_tokens + self._total_output_tokens
        print(f"\n{'=' * 60}")
        print("Session summary")
        print(f"  Task:    {self._task[:80]}")
        print(f"  Model:   {self._model}")
        print(f"  Status:  {self._status}")
        print(f"  Time:    {elapsed}s (LLM {llm_time}s, tools {tool_time}s)")
        print(f"  Tokens:  {total_tokens:,} "
              f"(in: {self._total_input_tokens:,}, "
              f"out: {self._total_output_tokens:,}, "
              f"cached: {self._total_cache_read_tokens:,})")
        if self._total_cost:
            print(f"  Cost:    ${self._total_cost:.4f}")
        print(f"  Calls:   {self._tool_count} tool calls, "
              f"{self._call_count} agent messages")
        if self._tool_counts:
            print("  Tools:")
            for name, count in sorted(
                self._tool_counts.items(), key=lambda x: -x[1]
            ):
                print(f"    {name}: {count}")
        print(f"  Log:     {self._path}")
        print(f"{'=' * 60}\n")


def _truncate_args(args: dict) -> dict:
    """Truncate large argument values for logging."""
    truncated = {}
    for k, v in args.items():
        s = str(v)
        truncated[k] = s[:500] if len(s) > 500 else s
    return truncated


def _fprint(msg: str) -> None:
    """Print a follow-mode message to stderr for live visibility."""
    import sys

    print(msg, file=sys.stderr, flush=True)


# Global instance — set by runner before tools are called
_current_log: ActionLog | None = None


def get_log() -> ActionLog | None:
    return _current_log


def set_log(log: ActionLog) -> None:
    global _current_log
    _current_log = log
