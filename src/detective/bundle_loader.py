"""Agent bundle loader — reads a bundle directory into an AgentBundle dataclass."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Bundles root: <repo>/agents/bundles/
_BUNDLES_ROOT = Path(__file__).resolve().parents[2] / "agents" / "bundles"


@dataclass
class AgentBundle:
    """A self-contained agent configuration loaded from disk.

    A bundle directory contains::

        bundle-name/
        ├── instructions.md              — system prompt template (required)
        ├── mcps.json                    — MCP server declarations (optional)
        ├── skills/
        │   └── <skill-name>/
        │       ├── SKILL.md             — skill instructions (required per skill)
        │       ├── scripts/*.py         — tool scripts with __tools__ lists (optional)
        │       └── references/*.md      — docs loaded into context (optional)
        └── knowledge/
            ├── memory-template.md       — initial memory file template (optional)
            └── *.md                     — static knowledge files (optional)
    """

    name: str
    instructions_template: str
    tools: list[Any] = field(default_factory=list)
    skill_dirs: list[str] = field(default_factory=list)
    knowledge_files: dict[str, str] = field(default_factory=dict)
    memory_template: str = ""
    seed_files: list[str] = field(default_factory=list)
    mcps: dict = field(default_factory=dict)
    bundle_path: Path = field(default_factory=lambda: Path("."))


def _load_tools(tools_dir: Path) -> list[Any]:
    """Import all .py files in *tools_dir* and collect their ``__tools__`` lists.

    Each tool script should define a module-level ``__tools__`` list containing
    ``@define_tool``-decorated tool objects (or any objects the Copilot SDK
    accepts as tools).

    *tools_dir* is typically ``skills/<name>/scripts/``.
    """
    tools: list[Any] = []
    for py_file in sorted(tools_dir.glob("*.py")):
        # Unique module name: bundle_skill_script (e.g. detective-v1_detective-kusto_site_tools)
        skill_name = tools_dir.parent.name
        bundle_name = tools_dir.parent.parent.parent.name
        mod_name = f"_bundle_tools_{bundle_name}_{skill_name}_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py_file)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        mod_tools = getattr(mod, "__tools__", [])
        tools.extend(mod_tools)
    return tools


def load_bundle(name: str) -> AgentBundle:
    """Load a bundle by name from the standard bundles directory.

    Args:
        name: Bundle name — must be a subdirectory of ``agents/bundles/``.

    Returns:
        A populated :class:`AgentBundle`.

    Raises:
        FileNotFoundError: If the bundle directory or ``instructions.md`` is missing.
    """
    bundle_dir = _BUNDLES_ROOT / name
    if not bundle_dir.is_dir():
        available = list_bundles()
        raise FileNotFoundError(
            f"Bundle '{name}' not found at {bundle_dir}. "
            f"Available bundles: {available}"
        )
    return load_bundle_from_path(bundle_dir)


def load_bundle_from_path(bundle_dir: Path) -> AgentBundle:
    """Load a bundle from an arbitrary directory path.

    Args:
        bundle_dir: Path to the bundle directory.

    Returns:
        A populated :class:`AgentBundle`.

    Raises:
        FileNotFoundError: If *bundle_dir* doesn't exist or ``instructions.md`` is missing.
    """
    bundle_dir = Path(bundle_dir).resolve()
    if not bundle_dir.is_dir():
        raise FileNotFoundError(f"Bundle directory does not exist: {bundle_dir}")

    # --- prompt.md (required, fallback to instructions.md) ---
    prompt_path = bundle_dir / "prompt.md"
    if not prompt_path.is_file():
        prompt_path = bundle_dir / "instructions.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(
            f"Bundle '{bundle_dir.name}' is missing prompt.md "
            f"(looked in {bundle_dir})"
        )
    instructions_template = prompt_path.read_text(encoding="utf-8")

    # --- skills/ (optional) ---
    # Each skill dir can contain SKILL.md, scripts/*.py, and references/*.md
    skill_dirs: list[str] = []
    tools: list[Any] = []
    knowledge_files: dict[str, str] = {}
    skills_root = bundle_dir / "skills"
    if skills_root.is_dir():
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                skill_dirs.append(str(child))
                # Load the skill instructions into knowledge so they appear in context
                skill_content = (child / "SKILL.md").read_text(encoding="utf-8")
                knowledge_files[f"skill-{child.name}"] = skill_content

                # Collect tool scripts from scripts/ inside this skill
                scripts_dir = child / "scripts"
                if scripts_dir.is_dir():
                    tools.extend(_load_tools(scripts_dir))
                # Collect reference docs from references/ inside this skill
                refs_dir = child / "references"
                if refs_dir.is_dir():
                    for md_file in sorted(refs_dir.glob("*.md")):
                        key = f"{child.name}/{md_file.name}"
                        knowledge_files[key] = md_file.read_text(encoding="utf-8")

    # --- knowledge/ (optional) ---
    memory_template = ""
    knowledge_root = bundle_dir / "knowledge"
    if knowledge_root.is_dir():
        for md_file in sorted(knowledge_root.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if md_file.name == "memory-template.md":
                memory_template = content
            else:
                knowledge_files[md_file.name] = content

    # --- mcps.json (optional) ---
    mcps: dict = {}
    mcps_path = bundle_dir / "mcps.json"
    if mcps_path.is_file():
        mcps = json.loads(mcps_path.read_text(encoding="utf-8"))

    # --- config.json (required — declares seed_files) ---
    config: dict = {}
    config_path = bundle_dir / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
    seed_files: list[str] = config.get("seed_files", [])

    return AgentBundle(
        name=bundle_dir.name,
        instructions_template=instructions_template,
        tools=tools,
        skill_dirs=skill_dirs,
        knowledge_files=knowledge_files,
        memory_template=memory_template,
        seed_files=seed_files,
        mcps=mcps,
        bundle_path=bundle_dir,
    )


def list_bundles() -> list[str]:
    """Return sorted names of all available bundles under ``agents/bundles/``.

    Only directories containing an ``instructions.md`` file are considered
    valid bundles.
    """
    if not _BUNDLES_ROOT.is_dir():
        return []
    return sorted(
        d.name
        for d in _BUNDLES_ROOT.iterdir()
        if d.is_dir()
        and ((d / "prompt.md").is_file() or (d / "instructions.md").is_file())
    )
