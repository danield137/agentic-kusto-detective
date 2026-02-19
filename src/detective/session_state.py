"""Session state persistence — tracks Copilot session IDs and metadata for resume."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def save_state(
    session_dir: Path,
    session_id: str,
    copilot_session_id: str,
    challenge_url: str,
    status: str = "running",
    model: str = "",
    bundle: str = "",
) -> Path:
    """Create or overwrite a session state file inside the session directory."""
    session_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "session_id": session_id,
        "copilot_session_id": copilot_session_id,
        "challenge_url": challenge_url,
        "status": status,
        "model": model,
        "bundle": bundle,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    path = session_dir / "session_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def load_state(session_dir: Path) -> dict[str, Any] | None:
    """Load a session state file. Returns None if not found."""
    path = session_dir / "session_state.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def update_status(session_dir: Path, status: str) -> None:
    """Update the status field in an existing session state file."""
    state = load_state(session_dir)
    if state is None:
        return
    state["status"] = status
    path = session_dir / "session_state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
