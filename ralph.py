"""Ralph Wiggum Loop — run the detective agent in iterating sessions.

Each iteration:
  1. Start a fresh session, seeded from the previous one
  2. Agent works on the challenge until it completes or times out
  3. Distill session findings into a structured summary
  4. Print the worklog diff showing what changed
  5. Latest session becomes the seed for the next iteration
  6. Repeat until solved or max_iterations reached

Usage:
    python ralph.py [max_iterations] [--seed <session_id>]

Example:
    python ralph.py 10
    python ralph.py 5 --seed session_20260306_231210
"""

import asyncio
import json
import sys

from dotenv import load_dotenv

load_dotenv()

from detective.runner import run_session  # noqa: E402
from detective.session_context import SESSIONS_DIR  # noqa: E402


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


async def ralph_loop(
    max_iterations: int = 5,
    seed_from: str = "",
    challenge_url: str = "https://detective.kusto.io/inbox",
    bundle: str = "detective-v1",
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

        try:
            action_log = await run_session(
                challenge_url,
                follow=True,
                seed_from=current_seed,
                bundle=bundle,
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


def main() -> None:
    args = sys.argv[1:]
    max_iterations = 5
    seed_from = ""
    bundle = "detective-v1"

    i = 0
    while i < len(args):
        if args[i] == "--seed" and i + 1 < len(args):
            seed_from = args[i + 1]
            i += 2
        elif args[i] == "--bundle" and i + 1 < len(args):
            bundle = args[i + 1]
            i += 2
        elif args[i].isdigit():
            max_iterations = int(args[i])
            i += 1
        else:
            i += 1

    asyncio.run(ralph_loop(
        max_iterations=max_iterations,
        seed_from=seed_from,
        bundle=bundle,
    ))


if __name__ == "__main__":
    main()
