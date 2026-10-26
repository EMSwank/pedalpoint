import pytest


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch, tmp_path):
    """Never read the developer's real ~/.pedalpoint (e.g. the backend file)."""
    home = tmp_path / "_home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture(autouse=True)
def _pin_platform(monkeypatch):
    """Pin platform to Linux/x86_64 so backend defaults are host-independent.

    Tests that need another platform override with their own monkeypatch.
    """
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
