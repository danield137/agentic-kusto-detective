"""E2E test — run the detective agent against synthetic challenges.

Starts the test server, runs the agent via run_session() with one
session per challenge (isolated metrics), and verifies results.

Requirements:
    - Azure credentials (az login)
    - DETECTIVE_CLUSTER_URI env var
    - MyDatabase with test data (run tests/setup_kusto.py first)
    - GITHUB_TOKEN env var for Copilot SDK

Usage:
    python -m pytest tests/test_e2e.py -v -m llm --run-llm
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import closing
from pathlib import Path

import pytest
import uvicorn

from run import run_session

TESTS_DIR = Path(__file__).parent
STATE_PATH = TESTS_DIR / "test_state.json"
CHALLENGES_PATH = TESTS_DIR / "challenges.json"


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _reset_state() -> None:
    """Reset test state to fresh."""
    STATE_PATH.write_text(
        json.dumps({"solved": {}, "submissions": [], "logged_in": False}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _read_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _load_challenges() -> list[dict]:
    import os
    cluster_uri = os.environ.get("DETECTIVE_CLUSTER_URI", "")
    raw = CHALLENGES_PATH.read_text(encoding="utf-8")
    raw = raw.replace("{cluster_uri}", cluster_uri)
    return json.loads(raw)


class _ServerThread:
    """Run the test server in a background thread."""

    def __init__(self, port: int):
        self.port = port
        self._server: uvicorn.Server | None = None
        self._thread: asyncio.Task | None = None

    async def start(self) -> None:
        from tests.test_server import app

        config = uvicorn.Config(
            app, host="127.0.0.1", port=self.port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = asyncio.create_task(self._server.serve())
        # Wait for server to be ready
        for _ in range(50):
            try:
                with closing(socket.create_connection(("127.0.0.1", self.port), timeout=0.5)):
                    return
            except OSError:
                await asyncio.sleep(0.1)
        raise RuntimeError(f"Test server didn't start on port {self.port}")

    async def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
        if self._thread:
            await self._thread


@pytest.fixture
async def test_server():
    """Start the test server and yield the base URL."""
    port = _find_free_port()
    _reset_state()
    server = _ServerThread(port)
    await server.start()
    yield f"http://127.0.0.1:{port}"
    await server.stop()


@pytest.mark.llm
@pytest.mark.asyncio
async def test_agent_solves_challenges_isolated(test_server: str):
    """Run one session per challenge, verifying metrics isolation."""
    challenges = _load_challenges()
    session_ids: list[str] = []

    for challenge in challenges:
        task = (
            f"Go to {test_server}/inbox and solve ONLY "
            f"'{challenge['name']}'. "
            f"Click on it in the sidebar, read the challenge, solve it, "
            f"submit the answer, then save_memory and STOP. "
            f"Do NOT work on any other challenge."
        )

        action_log = await run_session(
            challenge_url=f"{test_server}/inbox",
            follow=True,
            bundle="detective-v2",
            max_steps=50,
            task=task,
        )

        action_log.print_summary()
        session_ids.append(str(action_log.path.parent.name))

        # Verify this specific challenge was solved
        state = _read_state()
        assert challenge["slug"] in state.get("solved", {}), (
            f"Agent didn't solve {challenge['name']}. "
            f"Submissions: {state.get('submissions', [])}"
        )
        print(f"  ✅ {challenge['name']}: solved with "
              f"{action_log._tool_count} tools, "
              f"{action_log._total_input_tokens + action_log._total_output_tokens:,} tokens")

    # All solved
    state = _read_state()
    assert len(state.get("solved", {})) == len(challenges), (
        f"Expected {len(challenges)} solved, got {len(state.get('solved', {}))}"
    )
    print(f"\n  Session IDs for report: {', '.join(session_ids)}")
