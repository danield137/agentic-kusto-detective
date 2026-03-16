"""Reusable agent runner — used by both CLI and web server."""

import asyncio
import os
import shutil
import sys
import time
from collections.abc import Callable
from typing import Any

from copilot import CopilotClient, SessionConfig
from copilot.types import CustomAgentConfig, ResumeSessionConfig

from detective.action_log import ActionLog, set_log
from detective.bundle_loader import AgentBundle, load_bundle
from detective.handoff_tools import set_handoff_path
from detective.kusto_tools import set_cache_path
from detective.log_parser import generate_worklog
from detective.memory_tools import set_memory_path, set_memory_template
from detective.reasoning_tools import set_tree_path
from detective.session_context import SESSIONS_DIR, SessionContext
from detective.session_state import load_state, save_state, update_status

DEFAULT_BUNDLE = "detective-v1"

MODEL = "claude-opus-4.6-1m"

EXPERT_SYSTEM = (
    "You are a helpful expert consultant. Another AI agent is solving a "
    "Kusto Detective Agency challenge and has gotten stuck. They will "
    "describe what they've tried and ask for your advice. Be concise and "
    "actionable — give specific suggestions, not general encouragement. "
    "If you see a likely mistake in their approach, say so directly."
)


def _load_memory_context(ctx: SessionContext) -> str:
    """Read session memory file for the system prompt."""
    if not ctx.memory_path.exists():
        return ""
    content = ctx.memory_path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    return f"## Previous learnings\n{content}"


def _build_system_prompt(bundle: AgentBundle, ctx: SessionContext) -> str:
    """Build the system prompt from bundle instructions + knowledge + runtime context."""
    cluster_uri = os.environ.get("DETECTIVE_CLUSTER_URI", "<not configured>")
    memory_context = _load_memory_context(ctx)

    prompt = bundle.instructions_template.format(
        cluster_uri=cluster_uri,
        memory_context=memory_context,
        session_dir=str(ctx.session_dir),
        session_id=ctx.session_id,
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

    # Append distilled iteration summary from ralph loop if it exists
    summary_path = ctx.session_dir / "iteration_summary.md"
    if summary_path.exists():
        summary = summary_path.read_text(encoding="utf-8").strip()
        if summary:
            prompt += f"\n\n{summary}"

    return prompt


EventCallback = Callable[[dict[str, Any]], None]


REFLECTION_INTERVAL = 20  # Inject checkpoint every N tool calls
IDLE_TIMEOUT = 600  # Seconds to wait for session.idle before nudging
MAX_NUDGES = 5  # Force-exit after this many consecutive nudge timeouts

_REFLECTION_TEMPLATE = (
    "CHECKPOINT ({tc} tool calls). MANDATORY actions:\n"
    "1. STATE YOUR CURRENT SUB-PROBLEM in one sentence.\n"
    "2. Review `## Reasoning` in challenge.md — update stale entries.\n"
    "3. Call `save_memory` with findings + NEXT STEPS.\n"
    "4. If you have been working on the same approach for "
    "20+ tool calls without progress, call `write_handoff()` "
    "and STOP — your session will be restarted fresh.\n"
    "Then continue solving."
)


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
    """Copy persistent state files from a prior session."""
    src = SESSIONS_DIR / seed_id
    if not src.is_dir():
        print(f"Warning: seed session '{seed_id}' not found", file=sys.stderr)
        return
    for fname in seed_files:
        src_file = src / fname
        if src_file.exists():
            shutil.copy2(src_file, ctx.session_dir / fname)
    print(f"Seeded from {seed_id}", file=sys.stderr)


async def run_session(
    challenge_url: str,
    follow: bool = False,
    on_event: EventCallback | None = None,
    bundle: str = DEFAULT_BUNDLE,
    max_steps: int = 0,
    seed_from: str = "",
) -> ActionLog:
    """Run a detective agent session against a single challenge.

    Args:
        challenge_url: The challenge page URL.
        follow: If True, stream thinking/tool calls to stderr.
        on_event: Optional callback invoked for each SDK event (for SSE streaming).
        bundle: Name of the agent bundle to use (default: ``detective-v1``).
        max_steps: Stop after this many tool calls (0 = unlimited).
        seed_from: Optional session_id to copy memory, reasoning tree,
            and handoff from before starting.

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

    prompt_text = _build_system_prompt(agent_bundle, ctx)

    action_log = ActionLog(log_path=ctx.log_path, follow=follow, model=MODEL)
    set_log(action_log)
    session_id = ctx.session_id

    client = CopilotClient()
    await client.start()

    try:
        session_config: SessionConfig = {
            "model": MODEL,
            "system_message": {"mode": "replace", "content": prompt_text},
            "tools": agent_bundle.tools,
            "excluded_tools": ["store_memory"],
            "working_directory": str(ctx.session_dir),
            "custom_agents": [
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
            ],
        }
        # MCP servers declared in bundle mcps.json
        mcp_servers = agent_bundle.mcps.get("servers", {})
        if mcp_servers:
            session_config["mcp_servers"] = mcp_servers
        if follow:
            session_config["streaming"] = True

        session = await client.create_session(session_config)

        # Persist state for resume
        save_state(
            ctx.session_dir, session_id, session.session_id,
            challenge_url, model=MODEL, bundle=bundle,
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
        await session.send({
            "prompt": (
                f"Go to {challenge_url} and solve the first UNSOLVED case. "
                "Cases with a checkmark are already solved — skip them."
            ),
        })

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
                await session.send({"prompt": nudge})
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
                await session.send({"prompt": reflection})
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
                    await session.send({"prompt": reminder})
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
) -> ActionLog:
    """Resume an interrupted agent session.

    Args:
        session_id: The session_id to resume (e.g. 'session_20260220_210104').
        follow: If True, stream thinking/tool calls to stderr.
        on_event: Optional callback invoked for each SDK event (for SSE streaming).
        bundle: Name of the agent bundle to use (default: ``detective-v1``).
        max_steps: Stop after this many tool calls (0 = unlimited).

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

    action_log = ActionLog(log_path=ctx.log_path, follow=follow, model=MODEL)
    set_log(action_log)

    client = CopilotClient()
    await client.start()

    try:
        resume_config: ResumeSessionConfig = {
            "model": MODEL,
            "tools": agent_bundle.tools,
            "streaming": follow,
            "working_directory": str(ctx.session_dir),
            "custom_agents": [
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
            ],
        }
        mcp_servers = agent_bundle.mcps.get("servers", {})
        if mcp_servers:
            resume_config["mcp_servers"] = mcp_servers
        session = await client.resume_session(
            copilot_session_id,
            resume_config,
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
        await session.send(
            {
                "prompt": (
                    "The previous session was interrupted. Please continue where you left off. "
                    "Review what you've done so far and proceed with the next step."
                ),
            }
        )

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
                await session.send({"prompt": nudge})
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
                await session.send({"prompt": reflection})
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
                    await session.send({"prompt": reminder})
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
