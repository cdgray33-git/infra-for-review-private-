from pathlib import Path
import json
from typing import Dict

def ensure_agent_dir(agent_dir: Path):
    """
    Ensure the directory and parents exist and attempt to set safe permissions.
    """
    agent_dir.mkdir(parents=True, exist_ok=True)
    try:
        agent_dir.chmod(0o700)
    except Exception:
        # Non-fatal: ignore chmod errors on some mounts
        pass

def append_agent_log(agent_dir: Path, message: str):
    """
    Append a timestamped line to the agent log, ensuring the directory exists.
    """
    ensure_agent_dir(agent_dir)
    log_path = agent_dir / "log.txt"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")

def write_agent_state(agent_dir: Path, data: Dict):
    """
    Write JSON state for the agent, ensuring the directory exists.
    """
    ensure_agent_dir(agent_dir)
    state_path = agent_dir / "state.json"
    state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")