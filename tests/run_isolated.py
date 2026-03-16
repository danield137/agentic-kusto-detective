"""Run isolated E2E test — one session per challenge."""

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from detective.runner import run_session  # noqa: E402

CHALLENGES_PATH = Path(__file__).parent / "challenges.json"
STATE_PATH = Path(__file__).parent / "test_state.json"
SERVER = "http://127.0.0.1:8765"


async def main():
    challenges = json.loads(CHALLENGES_PATH.read_text(encoding="utf-8"))

    # Reset test state
    STATE_PATH.write_text(
        json.dumps({"solved": {}, "submissions": [], "logged_in": False}, indent=2),
        encoding="utf-8",
    )

    session_ids = []
    for c in challenges:
        name = c["name"]
        print(f"\n{'=' * 60}")
        print(f"  Running: {name}")
        print(f"{'=' * 60}")

        task = (
            f'Go to {SERVER}/inbox and solve ONLY "{name}". '
            f"Click on it in the sidebar, read the challenge, solve it, "
            f"submit the answer, then save_memory and STOP. "
            f"Do NOT work on any other challenge."
        )

        action_log = await run_session(
            challenge_url=f"{SERVER}/inbox",
            follow=True,
            bundle="detective-v2",
            max_steps=50,
            task=task,
        )
        action_log.print_summary()
        session_ids.append(str(action_log.path.parent.name))

    print(f"\nAll sessions: {session_ids}")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    print(f"Solved: {list(state.get('solved', {}).keys())}")

    # Print the range for generate_report.py
    if session_ids:
        print("\nGenerate report with:")
        print(f"  python generate_report.py --from {session_ids[0]} --to {session_ids[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
