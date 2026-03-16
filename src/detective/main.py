"""Entry point for the Kusto Detective agent."""

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()  # load .env before anything else

from detective.runner import resume_session, run_session  # noqa: E402


async def _run(
    challenge_url: str, follow: bool, bundle: str = "detective-v1",
    max_steps: int = 0, seed_from: str = "", task: str = "",
) -> None:
    action_log = await run_session(
        challenge_url, follow=follow, bundle=bundle,
        max_steps=max_steps, seed_from=seed_from, task=task,
    )
    print(f"Action log: {action_log.path}")
    action_log.print_summary()


async def _resume(
    session_id: str, follow: bool, bundle: str = "detective-v1",
    max_steps: int = 0,
) -> None:
    action_log = await resume_session(
        session_id, follow=follow, bundle=bundle, max_steps=max_steps,
    )
    print(f"Action log: {action_log.path}")
    action_log.print_summary()


def _extract_option(args: list[str], flag: str) -> tuple[str | None, list[str]]:
    """Extract a --flag <value> pair from args, returning (value, remaining_args)."""
    if flag not in args:
        return None, args
    idx = args.index(flag)
    if idx + 1 >= len(args):
        print(f"Error: {flag} requires an argument")
        sys.exit(1)
    value = args[idx + 1]
    remaining = args[:idx] + args[idx + 2:]
    return value, remaining


def main():
    args = sys.argv[1:]
    follow = False

    if "--follow" in args:
        follow = True
        args.remove("--follow")
    if "-f" in args:
        follow = True
        args.remove("-f")

    resume_id, args = _extract_option(args, "--resume")
    bundle, args = _extract_option(args, "--bundle")
    bundle = bundle or "detective-v1"
    max_steps_str, args = _extract_option(args, "--max-steps")
    max_steps = int(max_steps_str) if max_steps_str else 0
    seed_from, args = _extract_option(args, "--seed-from")
    seed_from = seed_from or ""
    task, args = _extract_option(args, "--task")
    task = task or ""

    if resume_id:
        asyncio.run(_resume(resume_id, follow=follow, bundle=bundle, max_steps=max_steps))
        return

    if not args:
        print("Usage: detective [--follow] [--bundle <name>] [--max-steps <n>]")
        print("       detective <challenge_url>")
        print("       detective [--follow] --resume <session_id>")
        print("       detective [--follow] --seed-from <session_id> <url>")
        print()
        print("Options:")
        print("  -f, --follow            Live stream agent thinking")
        print("  --resume <session_id>   Resume an interrupted session")
        print("  --seed-from <session_id> Start fresh but copy memory/tree")
        print("  --bundle <name>         Agent bundle (default: detective-v1)")
        print("  --task <instruction>    Scope session to a specific task")
        print("  --max-steps <n>         Stop after n tool calls (0 = unlimited)")
        print()
        print("Environment variables:")
        print("  DETECTIVE_CLUSTER_URI  Your free Kusto cluster URI for site login")
        sys.exit(1)

    challenge_url = args[0]
    asyncio.run(_run(
        challenge_url, follow=follow, bundle=bundle,
        max_steps=max_steps, seed_from=seed_from, task=task,
    ))


if __name__ == "__main__":
    main()
