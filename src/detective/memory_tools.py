"""Memory tools — single markdown file with sections and bullet points."""

from pathlib import Path

from copilot import define_tool
from pydantic import BaseModel, Field

_memory_path: Path | None = None
_memory_template: str = ""

_DEFAULT_MEMORY_TEMPLATE = """\
# Agent Memory

## Site Navigation

## KQL Patterns

## Case Solutions

## Learnings

## Open Questions
"""


def set_memory_path(path: Path) -> None:
    """Set the per-session memory file path."""
    global _memory_path
    _memory_path = path


def set_memory_template(template: str) -> None:
    """Set the memory template used when creating a new memory file.

    Called by the runner with the template from the active bundle.
    If never called, a built-in default is used.
    """
    global _memory_template
    _memory_template = template


def _ensure_memory() -> str:
    """Load memory file, creating with template if missing."""
    template = _memory_template or _DEFAULT_MEMORY_TEMPLATE
    if _memory_path is None:
        return template
    _memory_path.parent.mkdir(parents=True, exist_ok=True)
    if not _memory_path.exists():
        _memory_path.write_text(template, encoding="utf-8")
    return _memory_path.read_text(encoding="utf-8")


class SaveMemoryParams(BaseModel):
    section: str = Field(
        description=(
            "The section header to add the item under, e.g. "
            "'Site Navigation', 'KQL Patterns', 'Case Solutions', "
            "'Learnings', 'Open Questions'. Creates the section if missing."
        )
    )
    item: str = Field(
        description="A single bullet point to add (without the leading '- '). "
        "Keep it concise — one fact or learning per call."
    )


def _save_memory_impl(section: str, item: str) -> str:
    """Core save-memory logic — testable without the @define_tool wrapper."""
    try:
        content = _ensure_memory()
        header = f"## {section}"
        bullet = f"- {item}"

        if header in content:
            # Find the section and append the bullet after it
            lines = content.split("\n")
            new_lines = []
            inserted = False
            for i, line in enumerate(lines):
                new_lines.append(line)
                if line.strip() == header and not inserted:
                    # Find the end of this section (next ## or end of file)
                    # Insert before the next section or at end
                    j = i + 1
                    while j < len(lines) and not lines[j].startswith("## "):
                        j += 1
                    # Insert bullet just before the next section (or end)
                    # But after any existing bullets in this section
                    insert_at = j
                    for k in range(i + 1, j):
                        if lines[k].strip() == "":
                            continue
                        insert_at = k + 1
                    # Add the bullet at the right position
                    new_lines = lines[:insert_at] + [bullet] + lines[insert_at:]
                    inserted = True
                    break
            if inserted:
                content = "\n".join(new_lines)
            else:
                content = "\n".join(new_lines) + "\n" + bullet + "\n"
        else:
            # Add new section at end
            content = content.rstrip() + f"\n\n{header}\n{bullet}\n"

        if _memory_path is not None:
            _memory_path.write_text(content, encoding="utf-8")
        return f"Saved to [{section}]: {item[:80]}"
    except Exception as e:
        return f"Memory save error: {e}"


def _recall_memory_impl() -> str:
    """Core recall-memory logic — testable without the @define_tool wrapper."""
    return _ensure_memory()


@define_tool(
    description=(
        "Save a learning to persistent memory. Each call adds one bullet point "
        "under a section heading (e.g. 'Case Solutions', 'KQL Patterns', 'Learnings'). "
        "Call this whenever you discover something useful — after solving a case, "
        "after a failed attempt, or when you learn a new pattern. "
        "Memory persists across sessions."
    )
)
def save_memory(params: SaveMemoryParams) -> str:
    return _save_memory_impl(params.section, params.item)


@define_tool(
    description="Read the full memory file. Call this at the start of each session "
    "to load all accumulated knowledge from previous attempts."
)
def recall_memory() -> str:
    return _recall_memory_impl()
