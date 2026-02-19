"""SessionContext — single source of truth for all session-scoped paths."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detective.bundle_loader import AgentBundle

SESSIONS_DIR = Path(__file__).resolve().parents[2] / "sessions"


@dataclass
class SessionContext:
    """Encapsulates the session ID and all derived file paths.

    Every file the agent reads or writes during a session lives inside
    ``session_dir`` (``sessions/<session_id>/``).
    """

    session_id: str = field(default_factory=lambda: "")
    session_dir: Path = field(default_factory=lambda: Path())

    def __post_init__(self) -> None:
        if not self.session_id:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            self.session_id = f"session_{ts}"
        if self.session_dir == Path():
            self.session_dir = SESSIONS_DIR / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

    # -- derived paths --

    @property
    def log_path(self) -> Path:
        return self.session_dir / "session.jsonl"

    @property
    def state_path(self) -> Path:
        return self.session_dir / "session_state.json"

    @property
    def cache_path(self) -> Path:
        return self.session_dir / "kusto_cache.json"

    @property
    def memory_path(self) -> Path:
        return self.session_dir / "memory.md"

    @property
    def worklog_path(self) -> Path:
        return self.session_dir / "worklog.md"

    @property
    def reasoning_tree_path(self) -> Path:
        return self.session_dir / "reasoning_tree.json"

    @property
    def handoff_path(self) -> Path:
        return self.session_dir / "handoff.md"

    @property
    def cases_path(self) -> Path:
        return self.session_dir / "cases.md"

    @property
    def tasks_path(self) -> Path:
        return self.session_dir / "tasks.md"

    @property
    def skills_dir(self) -> Path:
        """`.github/skills/` inside the session — SDK auto-discovery location."""
        return self.session_dir / ".github" / "skills"

    def prepare_workspace(self, bundle: AgentBundle) -> None:
        """Copy the bundle's skills into the session directory.

        Creates ``session_dir/.github/skills/<skill>/`` so the Copilot CLI
        auto-discovers SKILL.md files from the ``working_directory``.
        """
        src_skills = bundle.bundle_path / "skills"
        if not src_skills.is_dir():
            return
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        for skill in sorted(src_skills.iterdir()):
            if skill.is_dir() and (skill / "SKILL.md").is_file():
                dest = self.skills_dir / skill.name
                shutil.copytree(skill, dest, dirs_exist_ok=True)
