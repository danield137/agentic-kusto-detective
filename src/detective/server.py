"""FastAPI web server — sessions dashboard with SSE live streaming."""

import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from detective.log_parser import list_sessions, parse_log_file
from detective.session_context import SESSIONS_DIR
from run import resume_session, run_session

app = FastAPI(title="Kusto Detective Dashboard")

app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track in-progress sessions: session_id -> {task, events, done, actual_session_id}
_active_sessions: dict[str, dict[str, Any]] = {}


class StartSessionRequest(BaseModel):
    challenge_url: str = "https://detective.kusto.io/inbox/onboarding"
    bundle: str = "detective-v3"
    challenge_num: int = 0


@app.get("/api/sessions")
async def get_sessions() -> list[dict[str, Any]]:
    """List all sessions with summary stats."""
    sessions = list_sessions(SESSIONS_DIR)
    # Annotate active sessions with "running" status
    for s in sessions:
        sid = s["session_id"]
        if sid in _active_sessions and not _active_sessions[sid]["done"]:
            s["status"] = "running"
    return sessions


@app.get("/api/sessions/{session_id}/events")
async def get_session_events(session_id: str) -> list[dict[str, Any]]:
    """Get all logged events for a specific session."""
    log_file = SESSIONS_DIR / session_id / "session.jsonl"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    events: list[dict[str, Any]] = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


@app.post("/api/sessions")
async def start_session_endpoint(req: StartSessionRequest) -> dict[str, str]:
    """Start a new agent session in the background."""
    # Generate a provisional session_id based on timestamp
    session_id = f"session_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}"

    event_buffer: list[dict[str, Any]] = []

    def on_event(event_data: dict[str, Any]) -> None:
        event_buffer.append(event_data)

    async def _run() -> None:
        try:
            action_log = await run_session(
                req.challenge_url,
                follow=False,
                on_event=on_event,
                bundle=req.bundle,
                challenge_num=req.challenge_num,
            )
            # Update session_id to match the actual session directory
            _active_sessions[session_id]["actual_session_id"] = action_log.path.parent.name
            action_log.print_summary()
        except Exception as e:
            event_buffer.append({"type": "error", "error": str(e)})
        finally:
            _active_sessions[session_id]["done"] = True
            event_buffer.append({"type": "done"})

    task = asyncio.create_task(_run())
    _active_sessions[session_id] = {
        "task": task,
        "events": event_buffer,
        "done": False,
        "actual_session_id": session_id,
    }

    return {"session_id": session_id, "status": "started"}


@app.post("/api/sessions/{session_id}/resume")
async def resume_session_endpoint(session_id: str) -> dict[str, str]:
    """Resume an interrupted agent session."""
    from detective.session_state import load_state

    session_dir = SESSIONS_DIR / session_id
    state = load_state(session_dir)
    if state is None:
        raise HTTPException(
            status_code=404, detail=f"No state file for session {session_id}"
        )

    event_buffer: list[dict[str, Any]] = []

    def on_event(event_data: dict[str, Any]) -> None:
        event_buffer.append(event_data)

    resume_key = f"resume_{session_id}"

    async def _run() -> None:
        try:
            action_log = await resume_session(
                session_id, follow=False, on_event=on_event
            )
            _active_sessions[resume_key]["actual_session_id"] = (
                action_log.path.parent.name
            )
            action_log.print_summary()
        except Exception as e:
            event_buffer.append({"type": "error", "error": str(e)})
        finally:
            _active_sessions[resume_key]["done"] = True
            event_buffer.append({"type": "done"})

    task = asyncio.create_task(_run())
    _active_sessions[resume_key] = {
        "task": task,
        "events": event_buffer,
        "done": False,
        "actual_session_id": resume_key,
    }

    return {"session_id": resume_key, "status": "resuming"}


@app.get("/api/sessions/{session_id}/stream")
async def stream_session(session_id: str) -> EventSourceResponse:
    """SSE stream of live events for an in-progress session."""
    if session_id not in _active_sessions:
        raise HTTPException(
            status_code=404, detail=f"Active session {session_id} not found"
        )

    session_state = _active_sessions[session_id]

    async def event_generator():
        cursor = 0
        while True:
            events = session_state["events"]
            while cursor < len(events):
                evt = events[cursor]
                cursor += 1
                yield {"event": evt.get("type", "unknown"), "data": json.dumps(evt)}
                if evt.get("type") == "done":
                    # Send final summary
                    actual_id = session_state.get(
                        "actual_session_id", session_id
                    )
                    log_file = SESSIONS_DIR / actual_id / "session.jsonl"
                    if log_file.exists():
                        summary = parse_log_file(log_file)
                        yield {
                            "event": "summary",
                            "data": json.dumps(summary),
                        }
                    return
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


def main() -> None:
    """Run the web server."""
    from dotenv import load_dotenv

    load_dotenv()

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)


if __name__ == "__main__":
    main()
