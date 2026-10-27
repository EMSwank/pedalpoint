"""Health checks for pedalpoint — used by `pedalpoint doctor`."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from pedalpoint import autostart, backends
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


def hf_hub_cache() -> Path:
    """Where huggingface_hub (and so mlx_lm) keeps downloaded models."""
    if os.getenv("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    if os.getenv("HF_HOME"):
        return Path(os.environ["HF_HOME"]) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _model_downloaded(model: str) -> bool:
    snapshots = hf_hub_cache() / f"models--{model.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


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


def check_backend(cfg: Config) -> CheckResult:
    """Check 2: PEDALPOINT_BACKEND is a supported backend."""
    if cfg.backend in backends.BACKENDS:
        return CheckResult("PASS", f"Backend: {cfg.backend}", None)
    return CheckResult(
        "FAIL",
        f"Unknown backend {cfg.backend!r}",
        "export PEDALPOINT_BACKEND=mlx",
    )


def check_server_reachable(
    cfg: Config,
    response: httpx.Response | None | _Unset = _UNSET,
) -> CheckResult:
    """Check 3: the local model server is reachable at the configured base URL.

    Pass a pre-fetched response (or None for unreachable) to avoid a second
    HTTP call when called from run_all.
    """
    if isinstance(response, _Unset):
        response = _fetch_models(cfg)
    name = backends.label(cfg)
    hint = backends.start_hint(cfg)
    if response is None and autostart.can_autostart(cfg):
        if autostart.find_mlx_server() is None:
            return CheckResult(
                "FAIL",
                "MLX not running and mlx_lm.server not found",
                "uv tool install mlx-lm",
            )
        return CheckResult(
            "WARN",
            "MLX not running — starts on the first local_llm call, "
            f"stops after {cfg.idle_minutes} idle minutes",
            None,
        )
    if response is None:
        return CheckResult("FAIL", f"{name} not reachable at {cfg.base_url}", hint)
    if response.status_code == 200:
        return CheckResult("PASS", f"{name} reachable at {cfg.base_url}", None)
    return CheckResult(
        "FAIL",
        f"{name} returned HTTP {response.status_code} at {cfg.base_url}",
        hint,
    )


def check_model_available(
    cfg: Config,
    response: httpx.Response | None | _Unset = _UNSET,
) -> CheckResult:
    """Check 4: the configured model is listed by the model server.

    Pass a pre-fetched response (or None for unreachable) to avoid a second
    HTTP call when called from run_all.  When response is None, the server is
    unreachable — the fix is to start it, not to download the model.
    """
    if isinstance(response, _Unset):
        response = _fetch_models(cfg)
    name = backends.label(cfg)
    start = backends.start_hint(cfg)
    if response is None and autostart.can_autostart(cfg):
        if _model_downloaded(cfg.model):
            return CheckResult("PASS", f"Model {cfg.model} downloaded", None)
        return CheckResult(
            "FAIL",
            f"Model {cfg.model} not downloaded",
            backends.pull_hint(cfg, cfg.model),
        )
    if response is None:
        return CheckResult(
            "FAIL",
            f"Model {cfg.model} check skipped — {name} unreachable at {cfg.base_url}",
            start,
        )
    if response.status_code != 200:
        return CheckResult(
            "FAIL",
            f"Model {cfg.model} check skipped"
            f" — {name} returned HTTP {response.status_code}",
            start,
        )
    # mlx_lm.server lists every model in the local HF cache by repo id, so for
    # mlx "available" means "downloaded" (verified with mlx-lm 0.32).
    models = [m["id"] for m in response.json().get("data", [])]
    if cfg.model in models:
        return CheckResult("PASS", f"Model {cfg.model} available", None)
    fix = backends.pull_hint(cfg, cfg.model)
    if cfg.backend == "mlx":
        fix += f" then restart: {start}"
    return CheckResult("FAIL", f"Model {cfg.model} not available", fix)


def check_pedalpoint_dir() -> CheckResult:
    """Check 5: ~/.pedalpoint/ directory exists (creates it if missing)."""
    pedalpoint_dir = Path.home() / ".pedalpoint"
    pedalpoint_dir.mkdir(parents=True, exist_ok=True)
    return CheckResult("PASS", "~/.pedalpoint/ exists", None)


def check_api_key(cfg: Config) -> CheckResult:
    """Check 6: ANTHROPIC_API_KEY is set (WARN if missing)."""
    if cfg.api_key:
        return CheckResult("PASS", "ANTHROPIC_API_KEY set", None)
    return CheckResult(
        "WARN",
        "ANTHROPIC_API_KEY not set (api_fallback tier disabled)",
        "export ANTHROPIC_API_KEY=sk-ant-...",
    )


# ── run all checks ───────────────────────────────────────────────────────────


def run_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all checks in order. Fetches /models once for the server checks."""
    if cfg is None:
        cfg = get_config()
    response = _fetch_models(cfg)
    return [
        check_binary_in_path(),
        check_backend(cfg),
        check_server_reachable(cfg, response),
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
