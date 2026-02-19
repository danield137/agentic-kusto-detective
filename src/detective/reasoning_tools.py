"""Reasoning tree tools — dependency-aware assumption tracking.

The agent builds a tree of assumptions where each node can depend on a parent.
When a node is invalidated, all descendants are automatically collapsed,
preventing wasted work on branches built on wrong foundations.
"""

import json
from pathlib import Path
from typing import Optional

from copilot import define_tool
from pydantic import BaseModel, Field

_tree_path: Path | None = None


def set_tree_path(path: Path) -> None:
    """Set the per-session reasoning tree file path."""
    global _tree_path
    _tree_path = path


def _load_tree() -> dict:
    """Load the reasoning tree from disk."""
    if _tree_path is None or not _tree_path.exists():
        return {}
    return json.loads(_tree_path.read_text(encoding="utf-8"))


def _save_tree(tree: dict) -> None:
    """Persist the reasoning tree to disk."""
    if _tree_path is None:
        return
    _tree_path.write_text(json.dumps(tree, indent=2), encoding="utf-8")


def _get_descendants(tree: dict, node_id: str) -> list[str]:
    """Return all descendant IDs of a node (children, grandchildren, etc.)."""
    descendants = []
    for nid, node in tree.items():
        if node.get("depends_on") == node_id:
            descendants.append(nid)
            descendants.extend(_get_descendants(tree, nid))
    return descendants


def _render_tree(tree: dict) -> str:
    """Render the tree as indented text."""
    if not tree:
        return "(empty tree)"

    # Find roots (nodes with no parent or parent not in tree)
    roots = [
        nid for nid, n in tree.items()
        if not n.get("depends_on") or n["depends_on"] not in tree
    ]

    lines: list[str] = []

    def _render_node(nid: str, depth: int) -> None:
        node = tree[nid]
        status = node["status"]
        indent = "  " * depth
        prefix = {
            "SOLID": "\u2705", "INVALID": "\u274c",
            "COLLAPSED": "\U0001f6ab", "HYPOTHESIS": "\u2753",
            "PARTIAL": "\u26a0\ufe0f",  # Warning sign for near-miss/partial
        }
        icon = prefix.get(status, "\u2753")
        line = f"{indent}{icon} {nid} [{status}]: {node['hypothesis']}"
        if node.get("evidence"):
            line += f" — {node['evidence']}"
        if node.get("reason"):
            line += f" — {node['reason']}"
        lines.append(line)
        # Render children
        children = [
            cid for cid, c in tree.items()
            if c.get("depends_on") == nid
        ]
        for cid in sorted(children):
            _render_node(cid, depth + 1)

    for root in sorted(roots):
        _render_node(root, 0)

    # Orphans (depends_on points to non-existent node)
    rendered = {nid for line in lines for nid in tree if nid in line}
    for nid in sorted(tree):
        if nid not in rendered:
            _render_node(nid, 0)

    return "\n".join(lines)


# --- Tool definitions ---


class AddAssumptionParams(BaseModel):
    id: str = Field(
        description="Short kebab-case ID (e.g., 'riddle-interp-1')",
    )
    depends_on: Optional[str] = Field(
        default=None,
        description="ID of parent assumption. None for root.",
    )
    hypothesis: str = Field(description="What you believe to be true. Be specific.")


@define_tool(
    description=(
        "Add an assumption to the reasoning tree. Each assumption can depend on "
        "a parent — if the parent is later invalidated, this assumption and all "
        "its descendants will be automatically collapsed. Use this to track your "
        "reasoning chain."
    )
)
def add_assumption(params: AddAssumptionParams) -> str:
    tree = _load_tree()
    if params.id in tree:
        return f"Error: assumption '{params.id}' already exists. Use a different ID."
    if params.depends_on and params.depends_on in tree:
        parent = tree[params.depends_on]
        if parent["status"] in ("INVALID", "COLLAPSED"):
            return (
                f"Error: parent '{params.depends_on}' is {parent['status']}. "
                "Cannot add assumptions under an invalidated branch."
            )
    tree[params.id] = {
        "hypothesis": params.hypothesis,
        "depends_on": params.depends_on,
        "status": "HYPOTHESIS",
        "evidence": None,
        "reason": None,
    }
    _save_tree(tree)
    return f"Added [{params.id}] as HYPOTHESIS under {params.depends_on or 'root'}."


class SolidifyParams(BaseModel):
    id: str = Field(description="ID of the assumption to confirm")
    evidence: str = Field(description="The evidence that confirms this assumption")


@define_tool(
    description=(
        "Mark an assumption as SOLID (confirmed with evidence). "
        "Only solidify assumptions you have verified with actual data or test results."
    )
)
def solidify(params: SolidifyParams) -> str:
    tree = _load_tree()
    if params.id not in tree:
        return f"Error: assumption '{params.id}' not found."
    node = tree[params.id]
    if node["status"] in ("INVALID", "COLLAPSED"):
        return f"Error: '{params.id}' is {node['status']} and cannot be solidified."
    node["status"] = "SOLID"
    node["evidence"] = params.evidence
    _save_tree(tree)
    return f"SOLIDIFIED [{params.id}]: {node['hypothesis']}"


class MarkPartialParams(BaseModel):
    id: str = Field(description="ID of the assumption")
    reason: str = Field(
        description="Why this is partial/suspicious "
        "(e.g., 'count off by 2', 'matches 3/4 clues')",
    )


@define_tool(
    description=(
        "Mark an assumption as PARTIAL/SUSPICIOUS. Use this when a result is "
        "close but not exact (e.g., off by 1-2%), or matches most but not all "
        "criteria. This keeps the branch open for further investigation without "
        "confirming it."
    )
)
def mark_partial(params: MarkPartialParams) -> str:
    tree = _load_tree()
    if params.id not in tree:
        return f"Error: assumption '{params.id}' not found."
    node = tree[params.id]
    if node["status"] in ("INVALID", "COLLAPSED"):
        return f"Error: '{params.id}' is {node['status']} and cannot be marked partial."

    node["status"] = "PARTIAL"
    node["evidence"] = f"(PARTIAL) {params.reason}"
    _save_tree(tree)
    return f"MARKED PARTIAL [{params.id}]: {params.reason}"


class InvalidateParams(BaseModel):
    id: str = Field(description="ID of the assumption to invalidate")
    reason: str = Field(description="Why this assumption is wrong")


@define_tool(
    description=(
        "Invalidate an assumption — marks it as INVALID and automatically "
        "COLLAPSES all descendant assumptions that depend on it. Returns the "
        "list of collapsed nodes so you know which work to abandon. "
        "Use this when evidence disproves a hypothesis."
    )
)
def invalidate(params: InvalidateParams) -> str:
    tree = _load_tree()
    if params.id not in tree:
        return f"Error: assumption '{params.id}' not found."
    node = tree[params.id]
    node["status"] = "INVALID"
    node["reason"] = params.reason

    # Collapse all descendants
    descendants = _get_descendants(tree, params.id)
    for did in descendants:
        tree[did]["status"] = "COLLAPSED"
        tree[did]["reason"] = f"Parent '{params.id}' was invalidated"

    _save_tree(tree)

    result = f"INVALIDATED [{params.id}]: {params.reason}"
    if descendants:
        result += f"\nCOLLAPSED {len(descendants)} dependent nodes: {', '.join(descendants)}"
        result += (
            "\n\nYou MUST now explore an alternative branch. "
            "Do NOT continue working on collapsed nodes."
        )
    return result


class ShowTreeParams(BaseModel):
    pass


@define_tool(
    description=(
        "Display the current reasoning tree showing all assumptions and their "
        "statuses (HYPOTHESIS, SOLID, INVALID, COLLAPSED). Use this to review "
        "your reasoning state and find unexplored branches."
    )
)
def show_tree(params: ShowTreeParams) -> str:
    tree = _load_tree()
    if not tree:
        return "Reasoning tree is empty. Use add_assumption to start building your reasoning chain."
    rendered = _render_tree(tree)
    # Count by status
    counts = {}
    for node in tree.values():
        s = node["status"]
        counts[s] = counts.get(s, 0) + 1
    summary = " | ".join(f"{s}: {c}" for s, c in sorted(counts.items()))
    return f"{rendered}\n\n--- {summary} ---"
