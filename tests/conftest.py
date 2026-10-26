import pytest


@pytest.fixture(autouse=True)
def _pin_platform(monkeypatch):
    """Pin platform to Linux/x86_64 so backend defaults are host-independent.

    Tests that need another platform override with their own monkeypatch.
    """
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
