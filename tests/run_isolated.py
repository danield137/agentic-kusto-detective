"""Run isolated E2E test — one session per challenge.

Usage:
    python tests/run_isolated.py                    # run all challenges (fresh start)
    python tests/run_isolated.py --force             # re-run all, even if solved
    python tests/run_isolated.py --case "Case 1 — Number Crunch"  # run one specific case
    python tests/run_isolated.py --force --case "Case 2 — Timezone Twist"
"""

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from run import run_session  # noqa: E402

CHALLENGES_PATH = Path(__file__).parent / "challenges.json"
STATE_PATH = Path(__file__).parent / "test_state.json"
SERVER = "http://127.0.0.1:8765"


def _reset_challenge(slug: str) -> None:
    """Reset a single challenge via the test server API."""
    req = urllib.request.Request(f"{SERVER}/api/reset/{slug}", method="POST")
    urllib.request.urlopen(req)


def _reset_all() -> None:
    """Reset all challenges via the test server API."""
    req = urllib.request.Request(f"{SERVER}/api/reset", method="POST")
    urllib.request.urlopen(req)


async def run_challenges(
    challenges: list[dict],
    force: bool = False,
    bundle: str = "detective-v2",
    max_steps: int = 50,
) -> list[str]:
    """Run one session per challenge, return session IDs."""
    if not force:
        _reset_all()

    session_ids = []
    for c in challenges:
        name = c["name"]
        slug = c["slug"]
        print(f"\n{'=' * 60}")
        print(f"  Running: {name}" + (" (force re-solve)" if force else ""))
        print(f"{'=' * 60}")

        if force:
            _reset_challenge(slug)

        task = (
            f'Go to {SERVER}/inbox and solve ONLY "{name}". '
            f"Click on it in the sidebar, read the challenge, solve it, "
            f"submit the answer, then save_memory and STOP. "
            f"Do NOT work on any other challenge."
        )
        if force:
            task += " Solve it even if it appears already completed."

        action_log = await run_session(
            challenge_url=f"{SERVER}/inbox",
            follow=True,
            bundle=bundle,
            max_steps=max_steps,
            task=task,
        )
        action_log.print_summary()
        session_ids.append(str(action_log.path.parent.name))

    return session_ids


def main() -> None:
    args = sys.argv[1:]
    force = "--force" in args
    if force:
        args.remove("--force")

    bundle = "detective-v2"
    if "--bundle" in args:
        idx = args.index("--bundle")
        bundle = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    max_steps = 50
    if "--max-steps" in args:
        idx = args.index("--max-steps")
        max_steps = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]

    case_filter = None
    if "--case" in args:
        idx = args.index("--case")
        case_filter = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    all_challenges = json.loads(CHALLENGES_PATH.read_text(encoding="utf-8"))

    if case_filter:
        challenges = [c for c in all_challenges if case_filter.lower() in c["name"].lower()]
        if not challenges:
            print(f"No challenge matching '{case_filter}'. Available:")
            for c in all_challenges:
                print(f"  - {c['name']}")
            sys.exit(1)
    else:
        challenges = all_challenges

    session_ids = asyncio.run(run_challenges(
        challenges, force=force, bundle=bundle, max_steps=max_steps,
    ))

    print(f"\nAll sessions: {session_ids}")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    print(f"Solved: {list(state.get('solved', {}).keys())}")

    if session_ids:
        print("\nGenerate report with:")
        print(f"  python generate_report.py --from {session_ids[0]} --to {session_ids[-1]}")


if __name__ == "__main__":
    main()
