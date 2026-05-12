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


def check_ollama_reachable(cfg: Config) -> CheckResult:
    """Check 2: Ollama is reachable at the configured base URL."""
    url = f"{cfg.base_url}/models"
    try:
        response = httpx.get(url, timeout=DOCTOR_TIMEOUT)
        if response.status_code == 200:
            return CheckResult(
                "PASS",
                f"Ollama reachable at {cfg.base_url}",
                None,
            )
        return CheckResult(
            "FAIL",
            f"Ollama returned HTTP {response.status_code} at {cfg.base_url}",
            "ollama serve",
        )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return CheckResult(
            "FAIL",
            f"Ollama not reachable at {cfg.base_url}",
            "ollama serve",
        )


def check_model_available(cfg: Config) -> CheckResult:
    """Check 3: Required model is available in Ollama."""
    url = f"{cfg.base_url}/models"
    try:
        response = httpx.get(url, timeout=DOCTOR_TIMEOUT)
        if response.status_code == 200:
            models = [m["id"] for m in response.json().get("data", [])]
            if cfg.model in models:
                return CheckResult(
                    "PASS",
                    f"Model {cfg.model} available",
                    None,
                )
            return CheckResult(
                "FAIL",
                f"Model {cfg.model} not available",
                f"ollama pull {cfg.model}",
            )
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        pass
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
    """Run all checks in order and return results."""
    if cfg is None:
        cfg = get_config()
    return [
        check_binary_in_path(),
        check_ollama_reachable(cfg),
        check_model_available(cfg),
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
