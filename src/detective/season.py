"""Season runner — run all challenges in sequence with memory carry-over."""

import asyncio
import json
import sys
from pathlib import Path

from detective.runner import run_session

# Season 2 challenges in order (discovered from detective.kusto.io/inbox).
# The agent navigates to each URL and the SPA renders the challenge.
SEASON_2_CASES: list[dict[str, str]] = [
    {"slug": "onboarding", "name": "Onboarding"},
    {"slug": "lieutenant-laughter", "name": "Lieutenant Laughter"},
    {"slug": "checkbox", "name": "Checkbox"},
]

BASE_URL = "https://detective.kusto.io/inbox"
RESULTS_DIR = Path("sessions")


def _load_season_progress() -> dict:
    """Load season progress from logs/season_progress.json."""
    path = RESULTS_DIR / "season_progress.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"completed": [], "results": {}}


def _save_season_progress(progress: dict) -> None:
    """Save season progress to logs/season_progress.json."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "season_progress.json"
    path.write_text(json.dumps(progress, indent=2, default=str), encoding="utf-8")


async def run_season(
    cases: list[dict[str, str]] | None = None,
    follow: bool = False,
    skip_completed: bool = True,
    bundle: str = "detective-v1",
) -> None:
    """Run all challenges in a season sequentially.

    Args:
        cases: List of case dicts with 'slug' and 'name'. Defaults to SEASON_2_CASES.
        follow: Stream agent output live.
        skip_completed: Skip cases already marked completed in season_progress.json.
        bundle: Name of the agent bundle to use.
    """
    if cases is None:
        cases = SEASON_2_CASES

    progress = _load_season_progress()

    print(f"🏁 Season runner: {len(cases)} cases")
    print(f"   Already completed: {progress['completed']}")
    print()

    for i, case in enumerate(cases):
        slug = case["slug"]
        name = case["name"]
        url = f"{BASE_URL}/{slug}"

        if skip_completed and slug in progress["completed"]:
            print(f"⏭️  [{i + 1}/{len(cases)}] {name} — already completed, skipping")
            continue

        print(f"🔍 [{i + 1}/{len(cases)}] {name}")
        print(f"   URL: {url}")
        print()

        try:
            action_log = await run_session(url, follow=follow, bundle=bundle)
            action_log.print_summary()

            progress["completed"].append(slug)
            progress["results"][slug] = {
                "status": "completed",
                "log_file": str(action_log.path),
                "agent_messages": action_log.call_count,
            }
        except KeyboardInterrupt:
            print(f"\n⚠️  Run interrupted during {name}")
            progress["results"][slug] = {"status": "interrupted"}
            _save_season_progress(progress)
            raise
        except Exception as e:
            print(f"❌ [{i + 1}/{len(cases)}] {name} — failed: {e}")
            progress["results"][slug] = {"status": "failed", "error": str(e)}

        _save_season_progress(progress)
        print()

    # Final summary
    print("=" * 60)
    print("🏆 Season Summary")
    total = len(cases)
    done = len(progress["completed"])
    print(f"   Completed: {done}/{total}")
    for slug in progress["completed"]:
        result = progress["results"].get(slug, {})
        print(f"   ✅ {slug}: {result.get('log_file', '?')}")
    for case in cases:
        if case["slug"] not in progress["completed"]:
            result = progress["results"].get(case["slug"], {})
            status = result.get("status", "not started")
            print(f"   ❌ {case['slug']}: {status}")
    print("=" * 60)


def main():
    args = sys.argv[1:]
    follow = False

    if "--follow" in args:
        follow = True
        args.remove("--follow")
    if "-f" in args:
        follow = True
        args.remove("-f")

    # Optional: run a single case by slug
    if args:
        slug = args[0]
        matching = [c for c in SEASON_2_CASES if c["slug"] == slug]
        if not matching:
            print(f"Unknown case slug: {slug}")
            print(f"Available: {[c['slug'] for c in SEASON_2_CASES]}")
            sys.exit(1)
        asyncio.run(run_season(matching, follow=follow, skip_completed=False))
    else:
        asyncio.run(run_season(follow=follow))


if __name__ == "__main__":
    main()
