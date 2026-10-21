"""Agent checkpoints in state/<run_id>.json so a crashed run can resume (task 8)."""
import json
from pathlib import Path

from instamart import config


def checkpoint_path(run_id: str) -> Path:
    """state/<run_id>.json."""
    return config.STATE_DIR / f"{run_id}.json"


def save(state: dict) -> None:
    """Write the full agent state atomically (temp file then rename)."""
    path = checkpoint_path(state["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def load(run_id: str) -> dict:
    """Read a checkpoint written by save."""
    return json.loads(checkpoint_path(run_id).read_text(encoding="utf-8"))


def clear_all() -> None:
    """Delete every checkpoint (state/.gitkeep stays) so a full run starts clean."""
    for path in config.STATE_DIR.glob("*.json"):
        path.unlink()
