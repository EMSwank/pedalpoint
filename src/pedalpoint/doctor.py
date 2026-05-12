"""Health checks for pedalpoint — used by `pedalpoint doctor`."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from pedalpoint.config import Config, get_config

# ── constants ────────────────────────────────────────────────────────────────

SEPARATOR = "─" * 38
DOCTOR_TIMEOUT = 5.0  # seconds — fail fast in CLI context


# ── result type ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckResult:
    status: Literal["PASS", "FAIL", "WARN"]
    message: str
    fix: str | None


# ── private sentinel & fetch helper ─────────────────────────────────────────


class _Unset:
    """Sentinel meaning 'no pre-fetched response — go fetch it yourself'."""


_UNSET = _Unset()


def _fetch_models(cfg: Config) -> httpx.Response | None:
    """GET /models once. Returns Response on success, None on connection failure."""
    try:
        return httpx.get(f"{cfg.base_url}/models", timeout=DOCTOR_TIMEOUT)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return None


# ── individual checks ────────────────────────────────────────────────────────


def check_binary_in_path() -> CheckResult:
    """Check 1: pedalpoint-server binary is in PATH."""
    found = shutil.which("pedalpoint-server")
    if found:
        return CheckResult("PASS", "pedalpoint-server in PATH", None)
    return CheckResult(
        "FAIL",
        "pedalpoint-server not found in PATH",
        "uv tool install pedalpoint",
    )


def check_ollama_reachable(
    cfg: Config,
    response: httpx.Response | None | _Unset = _UNSET,
) -> CheckResult:
    """Check 2: Ollama is reachable at the configured base URL.

    Pass a pre-fetched response (or None for unreachable) to avoid a second
    HTTP call when called from run_all.
    """
    if isinstance(response, _Unset):
        response = _fetch_models(cfg)
    if response is None:
        return CheckResult(
            "FAIL",
            f"Ollama not reachable at {cfg.base_url}",
            "ollama serve",
        )
    if response.status_code == 200:
        return CheckResult("PASS", f"Ollama reachable at {cfg.base_url}", None)
    return CheckResult(
        "FAIL",
        f"Ollama returned HTTP {response.status_code} at {cfg.base_url}",
        "ollama serve",
    )


def check_model_available(
    cfg: Config,
    response: httpx.Response | None | _Unset = _UNSET,
) -> CheckResult:
    """Check 3: Required model is available in Ollama.

    Pass a pre-fetched response (or None for unreachable) to avoid a second
    HTTP call when called from run_all.  When response is None, Ollama is
    unreachable — the fix is `ollama serve`, not `ollama pull`.
    """
    if isinstance(response, _Unset):
        response = _fetch_models(cfg)
    if response is None:
        return CheckResult(
            "FAIL",
            f"Model {cfg.model} check skipped — Ollama unreachable at {cfg.base_url}",
            "ollama serve",
        )
    if response.status_code != 200:
        return CheckResult(
            "FAIL",
            f"Model {cfg.model} check skipped"
            f" — Ollama returned HTTP {response.status_code}",
            "ollama serve",
        )
    models = [m["id"] for m in response.json().get("data", [])]
    if cfg.model in models:
        return CheckResult("PASS", f"Model {cfg.model} available", None)
    return CheckResult(
        "FAIL",
        f"Model {cfg.model} not available",
        f"ollama pull {cfg.model}",
    )


def check_pedalpoint_dir() -> CheckResult:
    """Check 4: ~/.pedalpoint/ directory exists (creates it if missing)."""
    pedalpoint_dir = Path.home() / ".pedalpoint"
    pedalpoint_dir.mkdir(parents=True, exist_ok=True)
    return CheckResult("PASS", "~/.pedalpoint/ exists", None)


def check_api_key(cfg: Config) -> CheckResult:
    """Check 5: ANTHROPIC_API_KEY is set (WARN if missing)."""
    if cfg.api_key:
        return CheckResult("PASS", "ANTHROPIC_API_KEY set", None)
    return CheckResult(
        "WARN",
        "ANTHROPIC_API_KEY not set (api_fallback tier disabled)",
        "export ANTHROPIC_API_KEY=sk-ant-...",
    )


# ── run all checks ───────────────────────────────────────────────────────────


def run_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all checks in order. Fetches /models once for checks 2 and 3."""
    if cfg is None:
        cfg = get_config()
    response = _fetch_models(cfg)
    return [
        check_binary_in_path(),
        check_ollama_reachable(cfg, response),
        check_model_available(cfg, response),
        check_pedalpoint_dir(),
        check_api_key(cfg),
    ]


# ── report formatting ─────────────────────────────────────────────────────────


def format_report(results: list[CheckResult]) -> tuple[str, int]:
    """Format the doctor report. Returns (text, exit_code)."""
    lines: list[str] = []
    lines.append("pedalpoint doctor")
    lines.append(SEPARATOR)

    for result in results:
        lines.append(f"{result.status}  {result.message}")
        if result.fix is not None:
            lines.append(f"      Fix: {result.fix}")

    lines.append(SEPARATOR)

    fail_count = sum(1 for r in results if r.status == "FAIL")

    if fail_count == 0:
        lines.append("All checks passed.")
        exit_code = 0
    elif fail_count == 1:
        lines.append(
            "1 check failed. Run the fix commands above, then re-run: pedalpoint doctor"
        )
        exit_code = 1
    else:
        lines.append(
            f"{fail_count} checks failed. Run the fix commands above,"
            " then re-run: pedalpoint doctor"
        )
        exit_code = 1

    return "\n".join(lines), exit_code
