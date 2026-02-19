"""Handoff tool — write a structured summary for session continuity.

When the agent is about to be reset (or proactively wants to checkpoint),
it writes a handoff document that captures everything a fresh session
needs to continue the investigation without re-deriving prior work.
"""

from pathlib import Path

from copilot import define_tool
from pydantic import BaseModel, Field

_handoff_path: Path | None = None


def set_handoff_path(path: Path) -> None:
    """Set the per-session handoff file path."""
    global _handoff_path
    _handoff_path = path


class WriteHandoffParams(BaseModel):
    confirmed_facts: str = Field(
        description=(
            "What you have CONFIRMED with evidence. "
            "Include methods, data, and results."
        ),
    )
    failed_approaches: str = Field(
        description=(
            "What you tried that FAILED and why. "
            "Be specific so the next session doesn't repeat."
        ),
    )
    current_hypothesis: str = Field(
        description="Your best current theory about the solution.",
    )
    next_steps: str = Field(
        description=(
            "Exactly what the next session should do FIRST. "
            "Be actionable and specific."
        ),
    )


@define_tool(
    description=(
        "Write a structured handoff summary for session continuity. "
        "Call this when you are about to be reset, or when you want "
        "to checkpoint your progress. The handoff document will be "
        "loaded into the next session so it can continue without "
        "re-deriving your work."
    )
)
def write_handoff(params: WriteHandoffParams) -> str:
    if _handoff_path is None:
        return "Error: handoff path not configured."

    content = (
        "# Session Handoff\n\n"
        "## Confirmed Facts\n"
        f"{params.confirmed_facts}\n\n"
        "## Failed Approaches (DO NOT REPEAT)\n"
        f"{params.failed_approaches}\n\n"
        "## Current Hypothesis\n"
        f"{params.current_hypothesis}\n\n"
        "## Next Steps (DO THIS FIRST)\n"
        f"{params.next_steps}\n"
    )
    _handoff_path.write_text(content, encoding="utf-8")
    return f"Handoff written to {_handoff_path.name}."
