import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pedalpoint.circuit_breaker import (
    CLOSED_STATE,
    compute_duration,
    double_duration,
    increment_rerouted,
    is_expired,
    read_state,
    transition_to_closed,
    transition_to_open,
    write_state,
)


# --- read_state ---

def test_read_state_absent_returns_closed(tmp_path: Path) -> None:
    assert read_state(tmp_path / "state.json") == {"circuit": "closed"}


def test_read_state_valid(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    data = {"circuit": "open", "failure_count": 2}
    p.write_text(json.dumps(data))
    assert read_state(p) == data


def test_read_state_corrupted_returns_closed(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    p.write_text("not valid json {{{")
    assert read_state(p) == {"circuit": "closed"}


# --- write_state ---

def test_write_state_creates_file(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    write_state({"circuit": "closed"}, p)
    assert json.loads(p.read_text()) == {"circuit": "closed"}


def test_write_state_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "state.json"
    write_state({"circuit": "closed"}, p)
    assert p.exists()


def test_write_state_overwrites_existing(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    write_state({"circuit": "open", "failure_count": 1}, p)
    write_state({"circuit": "closed"}, p)
    assert json.loads(p.read_text()) == {"circuit": "closed"}


# --- compute_duration ---

def test_compute_duration_failure_1() -> None:
    assert compute_duration(1) == 60


def test_compute_duration_failure_2() -> None:
    assert compute_duration(2) == 120


def test_compute_duration_failure_3() -> None:
    assert compute_duration(3) == 240


def test_compute_duration_failure_4() -> None:
    assert compute_duration(4) == 480


def test_compute_duration_caps_at_1440() -> None:
    assert compute_duration(100) == 1440


def test_compute_duration_custom_initial() -> None:
    assert compute_duration(1, initial_minutes=30) == 30
    assert compute_duration(2, initial_minutes=30) == 60


# --- is_expired ---

def test_is_expired_future() -> None:
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    assert not is_expired({"expires": expires})


def test_is_expired_past() -> None:
    expires = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    assert is_expired({"expires": expires})


def test_is_expired_missing_key() -> None:
    assert is_expired({})


# --- transition_to_open ---

def test_transition_to_open_sets_circuit() -> None:
    state = transition_to_open("402_quota")
    assert state["circuit"] == "open"


def test_transition_to_open_sets_reason() -> None:
    state = transition_to_open("402_quota")
    assert state["reason"] == "402_quota"


def test_transition_to_open_failure_count_default() -> None:
    state = transition_to_open("402_quota")
    assert state["failure_count"] == 1


def test_transition_to_open_duration_60_for_count_1() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    assert state["fallback_duration_minutes"] == 60


def test_transition_to_open_expires_in_future() -> None:
    state = transition_to_open("402_quota")
    expires = datetime.fromisoformat(state["expires"])
    assert expires > datetime.now(timezone.utc)


def test_transition_to_open_tasks_rerouted() -> None:
    state = transition_to_open("402_quota", tasks_rerouted=5)
    assert state["tasks_rerouted"] == 5


# --- transition_to_closed ---

def test_transition_to_closed() -> None:
    assert transition_to_closed() == {"circuit": "closed"}


# --- double_duration ---

def test_double_duration_increments_failure_count() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    doubled = double_duration(state)
    assert doubled["failure_count"] == 2


def test_double_duration_doubles_minutes() -> None:
    state = transition_to_open("402_quota", failure_count=1)
    doubled = double_duration(state)
    assert doubled["fallback_duration_minutes"] == 120


def test_double_duration_preserves_reason() -> None:
    state = transition_to_open("402_quota")
    doubled = double_duration(state)
    assert doubled["reason"] == "402_quota"


def test_double_duration_caps_at_1440() -> None:
    state = transition_to_open("402_quota", failure_count=10)
    doubled = double_duration(state)
    assert doubled["fallback_duration_minutes"] == 1440


# --- increment_rerouted ---

def test_increment_rerouted_starts_at_zero() -> None:
    state = transition_to_open("402_quota")
    assert state.get("tasks_rerouted", 0) == 0
    updated = increment_rerouted(state)
    assert updated["tasks_rerouted"] == 1


def test_increment_rerouted_accumulates() -> None:
    state = transition_to_open("402_quota")
    state = increment_rerouted(state)
    state = increment_rerouted(state)
    assert state["tasks_rerouted"] == 2
