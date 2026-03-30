"""Run — single source of truth for the detective agent runner.

This module contains ALL agent session logic:
  - run_session()    — run a single agent session
  - resume_session() — resume an interrupted session
  - ralph_loop()     — multi-iteration loop that seeds each session
                       from the previous one until solved

Usage:
    python run.py ralph --challenge-num 1 -i 5
    python run.py resume <session_id>
"""

import asyncio
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from copilot import CopilotClient, CustomAgentConfig, PermissionHandler  # noqa: E402

from detective.action_log import ActionLog, set_log  # noqa: E402
from detective.bundle_loader import AgentBundle, load_bundle  # noqa: E402
from detective.handoff_tools import set_handoff_path  # noqa: E402
from detective.kusto_tools import set_cache_path  # noqa: E402
from detective.log_parser import generate_worklog  # noqa: E402
from detective.memory_tools import set_memory_path, set_memory_template  # noqa: E402
from detective.reasoning_tools import set_tree_path  # noqa: E402
from detective.session_context import SESSIONS_DIR, SessionContext  # noqa: E402
from detective.session_state import load_state, save_state, update_status  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BUNDLE = "detective-v3"

MODEL = "claude-opus-4.6-1m"

EXPERT_SYSTEM = (
    "You are a helpful expert consultant. Another AI agent is solving a "
    "Kusto Detective Agency challenge and has gotten stuck. They will "
    "describe what they've tried and ask for your advice. Be concise and "
    "actionable — give specific suggestions, not general encouragement. "
    "If you see a likely mistake in their approach, say so directly."
)

REFLECTION_INTERVAL = 20  # Inject checkpoint every N tool calls
IDLE_TIMEOUT = 600  # Seconds to wait for session.idle before nudging
MAX_NUDGES = 5  # Force-exit after this many consecutive nudge timeouts

_REFLECTION_TEMPLATE = (
    "CHECKPOINT ({tc} tool calls). MANDATORY actions:\n"
    "1. STATE YOUR CURRENT SUB-PROBLEM in one sentence.\n"
    "2. Review `## Reasoning` in the current challenge file — update stale entries.\n"
    "3. Call `save_memory` with findings + NEXT STEPS.\n"
    "4. If you have been working on the same approach for "
    "20+ tool calls without progress, call `write_handoff()` "
    "and STOP — your session will be restarted fresh.\n"
    "Then continue solving."
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

EventCallback = Callable[[dict[str, Any]], None]

# ---------------------------------------------------------------------------
# Progress / utility functions
# ---------------------------------------------------------------------------


def _scan_challenge_progress(session_dir: Path) -> dict:
    """Scan challenge_*_case_*.md files to determine current progress.

    Returns a dict with:
        files: list of (filename, case_name, solved) tuples
        next_case_number: the case number to work on next
        challenge_num: the challenge number (season), or 0 if unknown
        summary: human-readable progress string for the resume prompt
    """
    # New naming: challenge_C_case_N.md  (e.g. challenge_2_case_3.md)
    challenge_files = sorted(session_dir.glob("challenge_*_case_*.md"))
    # Legacy fallback: challenge_N.md
    if not challenge_files:
        challenge_files = sorted(session_dir.glob("challenge_*.md"))
    if not challenge_files:
        return {"files": [], "next_case_number": 1, "challenge_num": 0,
                "summary": "No challenge files found."}

    files_info: list[tuple[str, str, bool]] = []
    detected_challenge_num = 0
    for f in challenge_files:
        content = f.read_text(encoding="utf-8")
        # Extract case name from first heading
        name_match = re.search(r"^#\s+(?:Challenge:\s*)?(.+)", content, re.MULTILINE)
        case_name = name_match.group(1).strip() if name_match else f.stem
        solved = bool(re.search(r"###?\s*Solution", content, re.IGNORECASE))
        files_info.append((f.name, case_name, solved))
        # Try to detect challenge number from filename
        cnum_match = re.search(r"challenge_(\d+)_case_", f.name)
        if cnum_match:
            detected_challenge_num = int(cnum_match.group(1))

    # Find the first unsolved case, or advance past the last solved
    next_num = None
    for fname, _cname, solved in files_info:
        if not solved:
            m = re.search(r"_case_(\d+)\.md$", fname)
            if not m:
                m = re.search(r"challenge_(\d+)\.md$", fname)
            if m:
                next_num = int(m.group(1))
            break

    if next_num is None:
        # All existing cases solved — advance to next case number
        last_file = challenge_files[-1]
        num_match = re.search(r"_case_(\d+)\.md$", last_file.name)
        if not num_match:
            num_match = re.search(r"challenge_(\d+)\.md$", last_file.name)
        last_num = int(num_match.group(1)) if num_match else 0
        next_num = last_num + 1

    # Build summary
    all_solved = all(solved for _, _, solved in files_info)
    lines = ["Challenge progress:"]
    for fname, cname, solved in files_info:
        status = "✅ SOLVED" if solved else "🔄 IN PROGRESS"
        lines.append(f"  - {fname}: {cname} — {status}")

    file_prefix = (
        f"challenge_{detected_challenge_num}_case_"
        if detected_challenge_num else "challenge_"
    )
    if all_solved:
        lines.append(f"\nAll existing cases solved. Next: create {file_prefix}{next_num}.md")
    else:
        # Find the first unsolved file for the summary
        first_unsolved = next(
            (fname, cname) for fname, cname, solved in files_info if not solved
        )
        lines.append(f"\nResume working on: {first_unsolved[0]} ({first_unsolved[1]})")

    return {
        "files": files_info,
        "next_case_number": next_num,
        "challenge_num": detected_challenge_num,
        "summary": "\n".join(lines),
    }


def _extract_hints(session_dir: Path) -> str:
    """Extract ``## Hint from human operator`` sections from case files.

    Returns all hints concatenated, or empty string if none found.
    """
    hints: list[str] = []
    for pattern in ("challenge_*_case_*.md", "challenge_*.md"):
        for f in sorted(session_dir.glob(pattern)):
            content = f.read_text(encoding="utf-8")
            match = re.search(
                r"^## Hint from human operator\s*\n(.+)",
                content,
                re.MULTILINE | re.DOTALL,
            )
            if match:
                hints.append(
                    f"[Hint for {f.name}]\n{match.group(1).strip()}"
                )
    return "\n\n".join(hints)


def _load_memory_context(ctx: SessionContext) -> str:
    """Read session memory file for the system prompt."""
    if not ctx.memory_path.exists():
        return ""
    content = ctx.memory_path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"## Previous learnings\n{content}"


def _build_system_prompt(bundle: AgentBundle, ctx: SessionContext,
                        challenge_num: int = 0) -> str:
    """Build the system prompt from bundle instructions + knowledge + runtime context."""
    cluster_uri = os.environ.get("DETECTIVE_CLUSTER_URI", "<not configured>")
    memory_context = _load_memory_context(ctx)

    prompt = bundle.instructions_template.format(
        cluster_uri=cluster_uri,
        memory_context=memory_context,
        session_dir=str(ctx.session_dir),
        session_id=ctx.session_id,
        challenge_num=challenge_num or "{{challenge_num}}",
    )

    # Append static knowledge files (everything in knowledge/ except memory-template.md)
    if bundle.knowledge_files:
        knowledge_parts = []
        for filename, content in sorted(bundle.knowledge_files.items()):
            knowledge_parts.append(content.strip())
        if knowledge_parts:
            prompt += "\n\n## Knowledge\n\n" + "\n\n".join(knowledge_parts)

    # Append handoff from previous session if it exists
    if ctx.handoff_path.exists():
        handoff = ctx.handoff_path.read_text(encoding="utf-8").strip()
        if handoff:
            prompt += f"\n\n## Prior Session Handoff\n{handoff}"

    # Append distilled iteration summary from the loop if it exists
    summary_path = ctx.session_dir / "iteration_summary.md"
    if summary_path.exists():
        summary = summary_path.read_text(encoding="utf-8").strip()
        if summary:
            prompt += f"\n\n{summary}"

    return prompt


def _make_event_handler(
    action_log: ActionLog,
    done: asyncio.Event,
    follow: bool,
    on_event: EventCallback | None,
) -> tuple[Callable[[Any], None], dict[str, float]]:
    """Create the shared event handler used by both run and resume.

    Returns (handler, activity) where activity["last"] is a monotonic timestamp
    updated on every SDK event.
    """

    _tool_count: dict[str, int] = {"count": 0, "last_reflection": 0}
    _activity: dict[str, float] = {"last": time.monotonic()}

    def _handle_event(event: Any) -> None:
        _activity["last"] = time.monotonic()
        etype = event.type.value
        if etype == "assistant.message":
            content = event.data.content or ""
            action_log.log_agent_message(content)
            if not follow:
                print(f"\nAgent: {content}\n")
            else:
                print(file=sys.stderr, flush=True)
        elif etype == "assistant.message_delta" and follow:
            delta = event.data.delta_content or ""
            print(delta, end="", file=sys.stderr, flush=True)
        elif etype == "assistant.reasoning_delta" and follow:
            delta = event.data.delta_content or ""
            print(delta, end="", file=sys.stderr, flush=True)
        elif etype == "assistant.reasoning" and follow:
            print(file=sys.stderr, flush=True)
        elif etype == "tool.execution_start":
            tool_name = getattr(event.data, "tool_name", None) or "unknown"
            args_str = getattr(event.data, "arguments", "") or ""
            call_id = getattr(event.data, "tool_call_id", "") or ""
            _tool_count["count"] += 1
            action_log.log_tool_start(
                tool_name, {"arguments": str(args_str)[:500]}
            )
        elif etype == "tool.execution_complete":
            tool_name = getattr(event.data, "tool_name", None) or "unknown"
            call_id = getattr(event.data, "tool_call_id", "") or ""
            result_obj = getattr(event.data, "result", None)
            if result_obj is not None:
                result = getattr(result_obj, "content", "") or ""
            else:
                result = ""
            action_log.log_tool_end(call_id, tool_name, result[:2000])
        elif etype == "assistant.usage":
            action_log.log_usage(
                input_tokens=int(getattr(event.data, "input_tokens", 0) or 0),
                output_tokens=int(getattr(event.data, "output_tokens", 0) or 0),
                cache_read_tokens=int(
                    getattr(event.data, "cache_read_tokens", 0) or 0
                ),
                cost=float(getattr(event.data, "cost", 0) or 0),
                model=getattr(event.data, "model", "") or "",
            )
        elif etype == "session.idle":
            done.set()

        if on_event is not None:
            on_event({"type": etype})

    return _handle_event, _activity


def _seed_session(
    ctx: SessionContext, seed_id: str, seed_files: list[str],
) -> None:
    """Copy persistent state files from a prior session.

    Supports glob patterns (e.g. ``challenge_*.md``) in *seed_files*.
    """
    src = SESSIONS_DIR / seed_id
    if not src.is_dir():
        print(f"Warning: seed session '{seed_id}' not found", file=sys.stderr)
        return
    import fnmatch
    for pattern in seed_files:
        if "*" in pattern or "?" in pattern:
            for src_file in src.iterdir():
                if src_file.is_file() and fnmatch.fnmatch(src_file.name, pattern):
                    shutil.copy2(src_file, ctx.session_dir / src_file.name)
        else:
            src_file = src / pattern
            if src_file.exists():
                shutil.copy2(src_file, ctx.session_dir / pattern)
    print(f"Seeded from {seed_id}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Core session functions
# ---------------------------------------------------------------------------


async def run_session(
    challenge_url: str,
    follow: bool = False,
    on_event: EventCallback | None = None,
    bundle: str = DEFAULT_BUNDLE,
    max_steps: int = 0,
    seed_from: str = "",
    task: str = "",
    challenge_num: int = 0,
    model: str = "",
) -> ActionLog:
    """Run a detective agent session against a single challenge.

    Args:
        challenge_url: The challenge page URL.
        follow: If True, stream thinking/tool calls to stderr.
        on_event: Optional callback invoked for each SDK event (for SSE streaming).
        bundle: Name of the agent bundle to use (default: ``detective-v3``).
        max_steps: Stop after this many tool calls (0 = unlimited).
        seed_from: Optional session_id to copy memory, reasoning tree,
            and handoff from before starting.
        task: Optional task instruction appended to the initial prompt.
            Use to scope the session to a specific challenge or action.
        challenge_num: The challenge/season number (e.g. 2 for Challenge II).
            Used for file naming: ``challenge_2_case_N.md``.

    Returns:
        The ActionLog instance with session results.
    """
    agent_bundle = load_bundle(bundle)
    ctx = SessionContext()

    # Seed state from a prior session if requested
    if seed_from:
        _seed_session(ctx, seed_from, agent_bundle.seed_files)

    # Wire per-session paths and bundle config into tool modules
    set_cache_path(ctx.cache_path)
    set_memory_path(ctx.memory_path)
    set_tree_path(ctx.reasoning_tree_path)
    set_handoff_path(ctx.handoff_path)
    if agent_bundle.memory_template:
        set_memory_template(agent_bundle.memory_template)

    # Copy bundle skills into session workspace for SDK auto-discovery
    ctx.prepare_workspace(agent_bundle)

    prompt_text = _build_system_prompt(agent_bundle, ctx, challenge_num=challenge_num)

    _model = model or MODEL
    action_log = ActionLog(log_path=ctx.log_path, follow=follow, model=_model)
    set_log(action_log)
    session_id = ctx.session_id

    client = CopilotClient()
    await client.start()

    try:
        _custom_agents = [
            CustomAgentConfig(
                name="gpt-expert",
                display_name="GPT Expert",
                description=(
                    "Ask GPT for a second opinion when stuck. "
                    "Formulate a clear question describing what "
                    "you've tried and what went wrong."
                ),
                prompt=EXPERT_SYSTEM,
            ),
            CustomAgentConfig(
                name="gemini-expert",
                display_name="Gemini Expert",
                description=(
                    "Ask Gemini for a second opinion when stuck. "
                    "Formulate a clear question describing what "
                    "you've tried and what went wrong."
                ),
                prompt=EXPERT_SYSTEM,
            ),
        ]
        mcp_servers = agent_bundle.mcps.get("servers", {}) or None

        session = await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model=_model,
            system_message={"mode": "replace", "content": prompt_text},
            tools=agent_bundle.tools,
            excluded_tools=["store_memory"],
            working_directory=str(ctx.session_dir),
            custom_agents=_custom_agents,
            mcp_servers=mcp_servers,
            streaming=follow or None,
        )

        # Persist state for resume
        save_state(
            ctx.session_dir, session_id, session.session_id,
            challenge_url, model=_model, bundle=bundle,
        )

        done = asyncio.Event()
        needs_reflection = asyncio.Event()
        handler, _activity = _make_event_handler(action_log, done, follow, on_event)

        # Patch the handler to trigger reflection at intervals
        _original_handler = handler
        _reflection_state = {"tool_count": 0, "last_reflection": 0, "saved_memory": False}

        def _counting_handler(event: Any) -> None:
            _original_handler(event)
            etype = event.type.value
            if etype == "tool.execution_start":
                tool_name = getattr(event.data, "tool_name", "")
                if tool_name == "save_memory":
                    _reflection_state["saved_memory"] = True

                _reflection_state["tool_count"] += 1
                since_last = _reflection_state["tool_count"] - _reflection_state["last_reflection"]
                if since_last >= REFLECTION_INTERVAL:
                    needs_reflection.set()
                if max_steps and _reflection_state["tool_count"] >= max_steps:
                    done.set()  # trigger exit from main loop

        session.on(_counting_handler)

        action_log.log_prompt(f"Solve the Kusto Detective challenge at: {challenge_url}")

        # Build the initial prompt — scope to the right case
        if task:
            initial_prompt = task + f"\n\nSite URL: {challenge_url}"
        else:
            progress = _scan_challenge_progress(ctx.session_dir)
            next_n = progress["next_case_number"]
            cnum = challenge_num or progress["challenge_num"]
            file_prefix = (
                f"challenge_{cnum}_case_"
                if cnum else "challenge_"
            )
            case_file = f"{file_prefix}{next_n}.md"
            case_exists = (ctx.session_dir / case_file).exists()

            nav_instructions = (
                f"Go to {challenge_url}. "
            )
            if cnum:
                nav_instructions += (
                    f"Click the 'Switch Challenge' button in the left sidebar "
                    f"to open Challenge {cnum}, then open Case {next_n}. "
                )
            else:
                nav_instructions += f"Open Case {next_n}. "

            if case_exists:
                # Resuming prior work — read case file first
                initial_prompt = (
                    f"You have prior work in {case_file} from a previous iteration. "
                    f"READ IT FIRST before doing anything else. "
                    f"Follow any instructions under '## Hint from human operator'. "
                    f"Then continue where you left off.\n\n"
                    + nav_instructions
                    + f"Solve ONLY Case {next_n} — do NOT move on to other cases. "
                    f"When done, call save_memory and STOP."
                )
            else:
                initial_prompt = (
                    nav_instructions
                    + f"Solve ONLY Case {next_n} — do NOT move on to other cases. "
                    f"IGNORE checkmarks on the site — only local files "
                    f"determine what's solved. "
                    f"Create {case_file} using a relative path "
                    f"(your working directory is already the session folder). "
                    f"When done, call save_memory and STOP."
                )
            if progress["summary"]:
                initial_prompt += f"\n\n{progress['summary']}"

        # Inject any human-operator hints directly into the prompt
        hints = _extract_hints(ctx.session_dir)
        if hints:
            initial_prompt += (
                f"\n\n⚠️ IMPORTANT — Human operator hints "
                f"(follow these IMMEDIATELY):\n{hints}"
            )
        await session.send(initial_prompt)

        # Main loop: poll for idle with activity-aware stuck detection
        _consecutive_nudges = 0
        while True:
            try:
                await asyncio.wait_for(done.wait(), timeout=5.0)
            except TimeoutError:
                # Check if there's been recent activity
                idle_for = time.monotonic() - _activity["last"]
                if idle_for < IDLE_TIMEOUT:
                    continue  # still active, keep waiting
                # No activity for IDLE_TIMEOUT seconds
                _consecutive_nudges += 1
                tc = _reflection_state["tool_count"]
                if _consecutive_nudges >= MAX_NUDGES:
                    action_log._status = "timeout"
                    if follow:
                        print(
                            f"\nAgent unresponsive after {MAX_NUDGES} nudges "
                            f"({tc} tools). Forcing exit.",
                            file=sys.stderr, flush=True,
                        )
                    break
                nudge = (
                    f"You appear to be stuck (no activity for {IDLE_TIMEOUT}s, "
                    f"{tc} tool calls so far). "
                    "Please continue solving the challenge. "
                    "If you've finished, call save_memory and stop."
                )
                action_log.log_prompt(nudge)
                if follow:
                    print(
                        f"\nNudge #{_consecutive_nudges} "
                        f"(idle {idle_for:.0f}s, {tc} tools)",
                        file=sys.stderr, flush=True,
                    )
                _activity["last"] = time.monotonic()  # reset after nudge
                await session.send(nudge)
                continue
            _consecutive_nudges = 0
            done.clear()

            # Check step limit
            if max_steps and _reflection_state["tool_count"] >= max_steps:
                action_log._status = "step_limit"
                if follow:
                    tc = _reflection_state["tool_count"]
                    print(
                        f"\n\u23f9 Step limit reached ({tc}/{max_steps} tool calls)",
                        file=sys.stderr, flush=True,
                    )
                break

            if needs_reflection.is_set():
                needs_reflection.clear()
                tc = _reflection_state["tool_count"]
                _reflection_state["last_reflection"] = tc
                reflection = _REFLECTION_TEMPLATE.format(tc=tc)
                action_log.log_prompt(reflection)
                if follow:
                    print(
                        f"\n⚡ Reflection checkpoint ({tc} tools)", file=sys.stderr, flush=True
                    )
                await session.send(reflection)
            else:
                # Check if save_memory was called
                if not _reflection_state["saved_memory"]:
                    reminder = (
                        "STOP. You have finished the task but have NOT called "
                        "save_memory as required. You MUST call save_memory now "
                        "with your findings, solution, and learnings before exiting."
                    )
                    action_log.log_prompt(reminder)
                    if follow:
                        print("\n⚠️  Enforcing save_memory...", file=sys.stderr, flush=True)
                    await session.send(reminder)
                    # We don't break here; we loop back to wait for the agent to act
                else:
                    action_log._status = "completed"
                    break  # Agent finished and saved memory

        update_status(ctx.session_dir, action_log._status)
        try:
            await asyncio.wait_for(session.destroy(), timeout=10)
        except (TimeoutError, Exception):
            pass  # session may not shut down cleanly after step limit
    except Exception:
        update_status(ctx.session_dir, "failed")
        action_log._status = "failed"
        raise
    finally:
        await client.stop()
        action_log.log_session_end()
        worklog = generate_worklog(action_log.path, ctx.worklog_path)
        if follow:
            print(f"Worklog: {worklog}", file=sys.stderr, flush=True)

    return action_log


async def resume_session(
    session_id: str,
    follow: bool = False,
    on_event: EventCallback | None = None,
    bundle: str = DEFAULT_BUNDLE,
    max_steps: int = 0,
    task: str = "",
    model: str = "",
) -> ActionLog:
    """Resume an interrupted agent session.

    Args:
        session_id: The session_id to resume (e.g. 'session_20260220_210104').
        follow: If True, stream thinking/tool calls to stderr.
        on_event: Optional callback invoked for each SDK event (for SSE streaming).
        bundle: Name of the agent bundle to use (default: ``detective-v1``).
        max_steps: Stop after this many tool calls (0 = unlimited).
        task: Optional task instruction to scope the resumed session.

    Returns:
        The ActionLog instance for the resumed session.
    """
    agent_bundle = load_bundle(bundle)
    ctx = SessionContext(session_id=session_id)

    # Wire per-session paths and bundle config into tool modules
    set_cache_path(ctx.cache_path)
    set_memory_path(ctx.memory_path)
    set_tree_path(ctx.reasoning_tree_path)
    set_handoff_path(ctx.handoff_path)
    if agent_bundle.memory_template:
        set_memory_template(agent_bundle.memory_template)

    # Ensure bundle skills are in session workspace (idempotent)
    ctx.prepare_workspace(agent_bundle)

    state = load_state(ctx.session_dir)
    if state is None:
        raise ValueError(f"No state file found for session '{session_id}'")

    copilot_session_id = state["copilot_session_id"]

    _model = model or MODEL
    action_log = ActionLog(log_path=ctx.log_path, follow=follow, model=_model)
    set_log(action_log)

    client = CopilotClient()
    await client.start()

    try:
        _custom_agents = [
            CustomAgentConfig(
                name="gpt-expert",
                display_name="GPT Expert",
                description="Ask GPT for a second opinion when stuck.",
                prompt=EXPERT_SYSTEM,
            ),
            CustomAgentConfig(
                name="gemini-expert",
                display_name="Gemini Expert",
                description="Ask Gemini for a second opinion when stuck.",
                prompt=EXPERT_SYSTEM,
            ),
        ]
        mcp_servers = agent_bundle.mcps.get("servers", {}) or None

        session = await client.resume_session(
            copilot_session_id,
            on_permission_request=PermissionHandler.approve_all,
            model=_model,
            tools=agent_bundle.tools,
            streaming=follow or None,
            working_directory=str(ctx.session_dir),
            custom_agents=_custom_agents,
            mcp_servers=mcp_servers,
        )

        done = asyncio.Event()
        needs_reflection = asyncio.Event()
        handler, _activity = _make_event_handler(action_log, done, follow, on_event)

        _original_handler = handler
        _reflection_state = {"tool_count": 0, "last_reflection": 0, "saved_memory": False}

        def _counting_handler(event: Any) -> None:
            _original_handler(event)
            if event.type.value == "tool.execution_start":
                tool_name = getattr(event.data, "tool_name", "")
                if tool_name == "save_memory":
                    _reflection_state["saved_memory"] = True

                _reflection_state["tool_count"] += 1
                since_last = _reflection_state["tool_count"] - _reflection_state["last_reflection"]
                if since_last >= REFLECTION_INTERVAL:
                    needs_reflection.set()
                if max_steps and _reflection_state["tool_count"] >= max_steps:
                    done.set()

        session.on(_counting_handler)

        action_log.log_prompt(f"Resuming session {session_id}")

        # Build a context-rich resume prompt from challenge files
        progress = _scan_challenge_progress(ctx.session_dir)
        resume_parts = [
            "The previous session was interrupted.",
            progress["summary"],
        ]
        if task:
            resume_parts.append(f"\nTask: {task}")
        else:
            if progress["files"]:
                last = progress["files"][-1]
                if last[2]:  # last case solved
                    resume_parts.append(
                        "\nThe case is solved. Call save_memory and STOP."
                    )
                else:
                    resume_parts.append(
                        f"\nContinue working on {last[0]}. "
                        f"Read it FIRST to see your progress and any hints. "
                        f"Solve ONLY this case — do NOT move on to other cases."
                    )
            else:
                resume_parts.append("\nReview what you've done so far and proceed.")

        # Inject any human-operator hints directly into the prompt
        hints = _extract_hints(ctx.session_dir)
        if hints:
            resume_parts.append(
                f"\n⚠️ IMPORTANT — Human operator hints "
                f"(follow these IMMEDIATELY):\n{hints}"
            )

        await session.send("\n".join(resume_parts))

        _consecutive_nudges = 0
        while True:
            try:
                await asyncio.wait_for(done.wait(), timeout=5.0)
            except TimeoutError:
                idle_for = time.monotonic() - _activity["last"]
                if idle_for < IDLE_TIMEOUT:
                    continue
                _consecutive_nudges += 1
                tc = _reflection_state["tool_count"]
                if _consecutive_nudges >= MAX_NUDGES:
                    action_log._status = "timeout"
                    if follow:
                        print(
                            f"\nAgent unresponsive after {MAX_NUDGES} nudges "
                            f"({tc} tools). Forcing exit.",
                            file=sys.stderr, flush=True,
                        )
                    break
                nudge = (
                    f"You appear to be stuck (no activity for {IDLE_TIMEOUT}s, "
                    f"{tc} tool calls so far). "
                    "Please continue solving the challenge. "
                    "If you've finished, call save_memory and stop."
                )
                action_log.log_prompt(nudge)
                if follow:
                    print(
                        f"\nNudge #{_consecutive_nudges} "
                        f"(idle {idle_for:.0f}s, {tc} tools)",
                        file=sys.stderr, flush=True,
                    )
                _activity["last"] = time.monotonic()
                await session.send(nudge)
                continue
            _consecutive_nudges = 0
            done.clear()

            # Check step limit
            if max_steps and _reflection_state["tool_count"] >= max_steps:
                action_log._status = "step_limit"
                if follow:
                    tc = _reflection_state["tool_count"]
                    print(
                        f"\nStep limit reached ({tc}/{max_steps} tool calls)",
                        file=sys.stderr, flush=True,
                    )
                break

            if needs_reflection.is_set():
                needs_reflection.clear()
                tc = _reflection_state["tool_count"]
                _reflection_state["last_reflection"] = tc
                reflection = _REFLECTION_TEMPLATE.format(tc=tc)
                action_log.log_prompt(reflection)
                if follow:
                    print(
                        f"\nReflection checkpoint ({tc} tools)", file=sys.stderr, flush=True
                    )
                await session.send(reflection)
            else:
                # Check if save_memory was called
                if not _reflection_state["saved_memory"]:
                    reminder = (
                        "STOP. You have finished the task but have NOT called "
                        "save_memory as required. You MUST call save_memory now "
                        "with your findings, solution, and learnings before exiting."
                    )
                    action_log.log_prompt(reminder)
                    if follow:
                        print("\nEnforcing save_memory...", file=sys.stderr, flush=True)
                    await session.send(reminder)
                else:
                    action_log._status = "completed"
                    break

        update_status(ctx.session_dir, action_log._status)
        try:
            await asyncio.wait_for(session.destroy(), timeout=10)
        except (TimeoutError, Exception):
            pass  # session may not shut down cleanly after step limit
    except Exception:
        update_status(ctx.session_dir, "failed")
        action_log._status = "failed"
        raise
    finally:
        await client.stop()
        action_log.log_session_end()
        worklog = generate_worklog(action_log.path, ctx.worklog_path)
        if follow:
            print(f"Worklog: {worklog}", file=sys.stderr, flush=True)

    return action_log

# ---------------------------------------------------------------------------
# Ralph-specific functions
# ---------------------------------------------------------------------------


def find_latest_session() -> str:
    """Find the most recent session directory name."""
    sessions = sorted(
        (d.name for d in SESSIONS_DIR.iterdir()
         if d.is_dir() and d.name.startswith("session_")),
        reverse=True,
    )
    return sessions[0] if sessions else ""


def _read_file(session_id: str, filename: str) -> str:
    """Read a file from a session directory, return empty if missing."""
    path = SESSIONS_DIR / session_id / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _distill_session(session_id: str) -> str:
    """Distill a session's artifacts into a structured iteration summary.

    Reads reasoning_tree.json, session.jsonl, and memory.md to produce
    a compact summary that carries forward to the next iteration's prompt.
    """
    parts: list[str] = []

    # --- Reasoning tree: extract confirmed, invalidated, and open hypotheses ---
    tree_raw = _read_file(session_id, "reasoning_tree.json")
    if tree_raw:
        try:
            tree = json.loads(tree_raw)
            solid = []
            partial = []
            invalid = []
            hypotheses = []
            for nid, node in tree.items():
                status = node.get("status", "HYPOTHESIS")
                hyp = node.get("hypothesis", "")
                evidence = node.get("evidence", "")
                reason = node.get("reason", "")
                if status == "SOLID":
                    detail = f"- ✅ **{nid}**: {hyp}"
                    if evidence:
                        detail += f" — Evidence: {evidence}"
                    solid.append(detail)
                elif status == "PARTIAL":
                    detail = f"- ⚠️ **{nid}**: {hyp}"
                    if evidence:
                        detail += f" — Note: {evidence}"
                    partial.append(detail)
                elif status == "INVALID":
                    detail = f"- ❌ **{nid}**: {hyp}"
                    if reason:
                        detail += f" — Reason: {reason}"
                    invalid.append(detail)
                elif status == "HYPOTHESIS":
                    hypotheses.append(f"- ❓ **{nid}**: {hyp}")
            if solid:
                parts.append("### Confirmed (SOLID)\n" + "\n".join(solid))
            if partial:
                parts.append(
                    "### ⚠️ PARTIAL / NEAR MISS (Requires Review)\n"
                    + "\n".join(partial)
                )
            if invalid:
                parts.append(
                    "### Failed approaches (INVALID — DO NOT REPEAT)\n"
                    + "\n".join(invalid)
                )
            if hypotheses:
                parts.append("### Open hypotheses\n" + "\n".join(hypotheses))

            # --- Contradiction detection ---
            # Check if any SOLID evidence mentions something an INVALID node rejected
            solid_evidence = " ".join(
                node.get("evidence", "") for node in tree.values()
                if node.get("status") == "SOLID" and node.get("evidence")
            )
            contradictions = []
            for nid, node in tree.items():
                if node.get("status") != "INVALID":
                    continue
                hyp_words = node.get("hypothesis", "").lower().split()
                # Check if key terms from the invalid hypothesis appear in solid evidence
                for word in hyp_words:
                    if len(word) > 5 and word in solid_evidence.lower():
                        contradictions.append(
                            f"- ⚠️ **{nid}** was INVALID but SOLID evidence "
                            f"references '{word}'. The core approach may be "
                            f"correct — investigate sub-details (tokenization, "
                            f"encoding, edge cases) instead of abandoning it."
                        )
                        break
            if contradictions:
                parts.append(
                    "### ⚠️ CONTRADICTIONS DETECTED\n"
                    + "\n".join(contradictions)
                )
        except json.JSONDecodeError:
            pass

    # --- Session log: extract key findings from agent messages & results ---
    log_raw = _read_file(session_id, "session.jsonl")
    if log_raw:
        key_findings: list[str] = []
        queries_run = 0
        answers_submitted: list[str] = []
        hints_used = 0
        total_tools = 0
        wall_clock = 0.0
        status = "unknown"

        for line in log_raw.splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            if ev.get("event") == "tool_start":
                total_tools += 1
                tool = ev.get("tool", "")
                if tool == "kusto_query":
                    queries_run += 1
                args_str = json.dumps(ev.get("args", {}))
                if "Hint" in args_str:
                    hints_used += 1

            if ev.get("event") == "agent_message":
                content = ev.get("content", "")
                # Capture messages with substantive findings
                lower = content.lower()
                if any(
                    kw in lower
                    for kw in [
                        "confirm",
                        "solidif",
                        "the hint",
                        "answer is",
                        "decoded",
                        "the leader",
                        "solution",
                    ]
                ):
                    key_findings.append(f"- {content[:200]}")

            if ev.get("event") == "tool_end":
                preview = ev.get("result_preview", "")
                # Capture answer submissions
                if "Submit" in preview or "answer" in preview.lower():
                    answers_submitted.append(preview[:150])

            if ev.get("event") == "session_end":
                wall_clock = ev.get("wall_clock_s", 0)
                status = ev.get("status", "unknown")

        stats = (
            f"### Session stats\n"
            f"- Status: {status}\n"
            f"- Tool calls: {total_tools}\n"
            f"- KQL queries: {queries_run}\n"
            f"- Hints used: {hints_used}\n"
            f"- Wall clock: {wall_clock:.0f}s"
        )
        parts.append(stats)

        if key_findings:
            parts.append(
                "### Key findings\n" + "\n".join(key_findings[:10])
            )
        if answers_submitted:
            parts.append(
                "### Answers submitted\n"
                + "\n".join(f"- {a}" for a in answers_submitted)
            )

    # --- Memory: include if non-empty ---
    memory = _read_file(session_id, "memory.md")
    if memory and "## " in memory:
        # Check if any section has actual content
        has_content = False
        for line in memory.splitlines():
            if line.strip() and not line.startswith("#") and not line.startswith("---"):
                has_content = True
                break
        if has_content:
            parts.append(f"### Agent memory\n{memory}")

    if not parts:
        return ""

    summary = "---\n\n## Previous iteration summary\n\n" + "\n\n".join(parts)

    # Write to session directory
    summary_path = SESSIONS_DIR / session_id / "iteration_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"  Distilled summary → {summary_path.name}")

    return summary


def _print_worklog_diff(
    prev_session: str, curr_session: str,
) -> None:
    """Print what changed in worklog between iterations."""
    prev = _read_file(prev_session, "worklog.md") if prev_session else ""
    curr = _read_file(curr_session, "worklog.md")

    if not curr:
        print("  (no worklog produced)")
        return

    # Show only the new lines added since last session
    prev_lines = set(prev.splitlines())
    new_lines = [
        ln for ln in curr.splitlines() if ln not in prev_lines and ln.strip()
    ]

    if new_lines:
        print("\n--- Worklog Diff ---")
        for ln in new_lines:
            print(f"  {ln}")
        print("--- End Diff ---\n")
    else:
        print("  (worklog unchanged)")

# ---------------------------------------------------------------------------
# Ralph loop
# ---------------------------------------------------------------------------


async def ralph_loop(
    max_iterations: int = 5,
    seed_from: str = "",
    challenge_url: str = "https://detective.kusto.io/inbox",
    bundle: str = "detective-v3",
    task: str = "",
    challenge_num: int = 0,
    follow: bool = True,
    max_steps: int = 0,
    model: str = "",
) -> None:
    """Run the Ralph loop."""
    print("=" * 60)
    print("  Ralph Wiggum Loop — Detective Agent")
    print(f"  Max iterations: {max_iterations}")
    print(f"  Challenge: {challenge_url}")
    print(f"  Bundle: {bundle}")
    print("=" * 60)

    current_seed = seed_from

    for i in range(1, max_iterations + 1):
        print(f"\n{'=' * 60}")
        print(f"  Iteration {i} of {max_iterations}")
        if current_seed:
            print(f"  Seeding from: {current_seed}")
        else:
            print("  Starting fresh (no seed)")
        print(f"{'=' * 60}\n")

        prev_session = current_seed

        # Build task from seeded challenge files if not explicitly set
        iter_task = task
        if not iter_task and current_seed:
            progress = _scan_challenge_progress(
                SESSIONS_DIR / current_seed,
            )
            if progress["files"]:
                next_n = progress["next_case_number"]
                cnum = challenge_num or progress["challenge_num"]
                file_prefix = f"challenge_{cnum}_case_" if cnum else "challenge_"
                nav = f"Go to {challenge_url}. "
                if cnum:
                    nav += (
                        f"Click 'Switch Challenge' in the left sidebar "
                        f"to open Challenge {cnum}, then open Case {next_n}. "
                    )
                else:
                    nav += f"Open Case {next_n}. "
                iter_task = (
                    nav
                    + f"Solve ONLY Case {next_n} — do NOT move on to other cases. "
                    f"IGNORE checkmarks on the site — only local files "
                    f"determine completion. "
                    f"Create {file_prefix}{next_n}.md with your work. "
                    f"When done, call save_memory and STOP."
                )
                print(f"  Auto-task: solve Case {next_n}")

        try:
            action_log = await run_session(
                challenge_url,
                follow=follow,
                seed_from=current_seed,
                bundle=bundle,
                task=iter_task,
                challenge_num=challenge_num,
                max_steps=max_steps,
                model=model,
            )
            action_log.print_summary()

            # Find the session that was just created
            current_seed = find_latest_session()

            # Print worklog diff
            _print_worklog_diff(prev_session, current_seed)

            if action_log._status == "completed":
                print(f"\n{'=' * 60}")
                print(f"  Ralph solved the challenge at iteration {i}!")
                print(f"{'=' * 60}")
                return
        except Exception as e:
            print(f"  Session error: {e}", file=sys.stderr)
            current_seed = find_latest_session()

        # Distill session findings for the next iteration (always, even on failure)
        if current_seed and current_seed != prev_session:
            try:
                _distill_session(current_seed)
            except Exception as de:
                print(f"  Distillation error: {de}", file=sys.stderr)

        print(f"  Next seed: {current_seed}")

    print(f"\n{'=' * 60}")
    print(f"  Ralph reached max iterations ({max_iterations})")
    print(f"  Latest session: {current_seed}")
    print(f"{'=' * 60}")

# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


import click  # noqa: E402


@click.group()
def cli() -> None:
    """Kusto Detective Agent — solve challenges with AI."""


@cli.command()
@click.option("-i", "--iterations", default=5, help="Max iterations.")
@click.option("--seed", "seed_from", default="", help="Seed from a prior session.")
@click.option("--url", default="https://detective.kusto.io/inbox", help="Challenge URL.")
@click.option("--bundle", default="detective-v3", help="Agent bundle name.")
@click.option("--task", default="", help="Custom task instruction.")
@click.option("--challenge-num", default=0, type=int, help="Challenge/season number.")
@click.option("-f", "--follow/--no-follow", default=True, help="Stream agent output.")
@click.option("--max-steps", default=0, type=int, help="Stop after N tool calls.")
@click.option("--model", default="", help="Override the LLM model.")
def ralph(
    iterations: int, seed_from: str, url: str, bundle: str,
    task: str, challenge_num: int, follow: bool, max_steps: int,
    model: str,
) -> None:
    """Run the iterating solve loop."""
    asyncio.run(ralph_loop(
        max_iterations=iterations,
        seed_from=seed_from,
        challenge_url=url,
        bundle=bundle,
        task=task,
        challenge_num=challenge_num,
        follow=follow,
        max_steps=max_steps,
        model=model,
    ))


@cli.command()
@click.argument("session_id")
@click.option("--bundle", default="detective-v3", help="Agent bundle name.")
@click.option("-f", "--follow/--no-follow", default=True, help="Stream agent output.")
@click.option("--max-steps", default=0, type=int, help="Stop after N tool calls.")
@click.option("--task", default="", help="Custom task instruction.")
@click.option("--model", default="", help="Override the LLM model.")
def resume(
    session_id: str, bundle: str, follow: bool,
    max_steps: int, task: str, model: str,
) -> None:
    """Resume an interrupted session."""
    action_log = asyncio.run(resume_session(
        session_id, follow=follow, bundle=bundle,
        max_steps=max_steps, task=task, model=model,
    ))
    action_log.print_summary()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
