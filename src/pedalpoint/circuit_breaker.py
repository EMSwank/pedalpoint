import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CircuitState = dict[str, Any]

CLOSED_STATE: CircuitState = {"circuit": "closed"}

DEFAULT_STATE_PATH = Path.home() / ".pedalpoint" / "state.json"


def read_state(path: Path = DEFAULT_STATE_PATH) -> CircuitState:
    if not path.exists():
        return CLOSED_STATE.copy()
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return CLOSED_STATE.copy()


def write_state(state: CircuitState, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(path)


def compute_duration(failure_count: int, initial_minutes: int = 60) -> int:
    return min(initial_minutes * (2 ** (failure_count - 1)), 1440)


def is_expired(state: CircuitState) -> bool:
    expires = state.get("expires")
    if not expires:
        return True
    return datetime.now(timezone.utc) >= datetime.fromisoformat(expires)


def transition_to_open(
    reason: str,
    failure_count: int = 1,
    initial_minutes: int = 60,
    tasks_rerouted: int = 0,
) -> CircuitState:
    now = datetime.now(timezone.utc)
    duration = compute_duration(failure_count, initial_minutes)
    return {
        "circuit": "open",
        "reason": reason,
        "opened_at": now.isoformat(),
        "expires": (now + timedelta(minutes=duration)).isoformat(),
        "failure_count": failure_count,
        "fallback_duration_minutes": duration,
        "tasks_rerouted": tasks_rerouted,
    }


def transition_to_closed() -> CircuitState:
    return CLOSED_STATE.copy()


def double_duration(
    state: CircuitState, initial_minutes: int = 60
) -> CircuitState:
    failure_count = state.get("failure_count", 1) + 1
    return transition_to_open(
        reason=state.get("reason", "unknown"),
        failure_count=failure_count,
        initial_minutes=initial_minutes,
        tasks_rerouted=state.get("tasks_rerouted", 0),
    )


def increment_rerouted(state: CircuitState) -> CircuitState:
    return {**state, "tasks_rerouted": state.get("tasks_rerouted", 0) + 1}
