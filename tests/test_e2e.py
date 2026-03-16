"""E2E test — run the detective agent against synthetic challenges.

Starts the test server, runs the agent via run_session(), and verifies
that challenges were solved by checking test_state.json.

Requirements:
    - Azure credentials (az login)
    - DETECTIVE_CLUSTER_URI env var
    - TestChallenges database with test data (run tests/setup_kusto.py first)
    - GITHUB_TOKEN env var for Copilot SDK

Usage:
    python -m pytest tests/test_e2e.py -v -m llm
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import closing
from pathlib import Path

import pytest
import uvicorn

from detective.runner import run_session

TESTS_DIR = Path(__file__).parent
STATE_PATH = TESTS_DIR / "test_state.json"


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
async def test_agent_solves_first_challenge(test_server: str):
    """Run agent against the test server and verify it solves at least one challenge."""
    action_log = await run_session(
        challenge_url=f"{test_server}/inbox",
        follow=True,
        bundle="detective-v2",
        max_steps=80,
    )

    action_log.print_summary()

    state = _read_state()
    solved = state.get("solved", {})

    # Agent should have solved at least the first challenge
    assert len(solved) >= 1, (
        f"Agent didn't solve any challenges. "
        f"Submissions: {state.get('submissions', [])}"
    )

    # Check that the answer was correct
    for slug, info in solved.items():
        print(f"  ✅ {slug}: answer={info['answer']}")


@pytest.mark.llm
@pytest.mark.asyncio
async def test_agent_solves_all_challenges(test_server: str):
    """Run agent with enough steps to attempt all 3 challenges."""
    action_log = await run_session(
        challenge_url=f"{test_server}/inbox",
        follow=True,
        bundle="detective-v2",
        max_steps=200,
    )

    action_log.print_summary()

    state = _read_state()
    solved = state.get("solved", {})

    print(f"\n  Solved {len(solved)}/3 challenges:")
    for slug, info in solved.items():
        print(f"    ✅ {slug}: answer={info['answer']}")

    unsolved = {"number-crunch", "timezone-twist", "final-count"} - set(solved.keys())
    if unsolved:
        print(f"    ❌ Unsolved: {unsolved}")

    assert len(solved) == 3, (
        f"Agent solved {len(solved)}/3 challenges. "
        f"Unsolved: {unsolved}. "
        f"Submissions: {json.dumps(state.get('submissions', []), indent=2)}"
    )
