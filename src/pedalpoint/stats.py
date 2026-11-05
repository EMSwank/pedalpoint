"""Net Claude tokens saved by local handoffs — the math behind `pedalpoint stats`.

Avoided = changed_tokens (what Claude would have written doing the task itself).
Cost    = Claude output spent issuing the call + reviewing/fixing the draft,
          measured from transcripts when possible, else estimated from the score.

Input is reported beside that, never folded in: Anthropic doesn't publish how plan
limits weigh new and cached input, so any single score would rest on a guess.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from pedalpoint.transcripts import HandoffCost

ESTIMATED_CALL_COST = 100
REWRITE_SHARE = {7: 0.0, 6: 0.1, 5: 0.3, 4: 0.5, 3: 0.75, 2: 0.9, 1: 1.0}
VERDICT_NOTE = (
    "The verdict covers output tokens and scores only. Weigh it against input\n"
    "yourself: Anthropic doesn't publish how plan limits count new and cached input."
)


@dataclass(frozen=True)
class Handoff:
    handoff_id: str
    ts: datetime
    model: str
    backend: str
    completion_tokens: int
    changed_tokens: int
    score: int | None


@dataclass(frozen=True)
class Row:
    model: str
    week: str
    handoffs: int
    unscored: int
    avg_score: float | None
    redo_rate: float | None
    local_tokens: int
    net_output: int
    new_input: int | None  # None: no handoff in this row was measured
    cached_input: int | None
    pct_estimated: float
    paying_off: bool


def join_records(records: list[dict]) -> list[Handoff]:
    """Join call records with their latest outcome; skip malformed calls."""
    scores = {
        r["handoff_id"]: r.get("score")
        for r in records
        if r.get("kind") == "outcome" and "handoff_id" in r
    }
    handoffs = []
    for r in records:
        if r.get("kind") != "call":
            continue
        try:
            handoffs.append(
                Handoff(
                    handoff_id=r["handoff_id"],
                    ts=datetime.fromisoformat(r["ts"]),
                    model=r["model"],
                    backend=r["backend"],
                    completion_tokens=int(r["completion_tokens"]),
                    changed_tokens=int(r["changed_tokens"]),
                    score=scores.get(r["handoff_id"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return handoffs


def net_saved(h: Handoff, cost: HandoffCost | None) -> tuple[int, bool]:
    """Return (net_output_saved, estimated)."""
    if cost is not None and cost.complete:
        return h.changed_tokens - cost.call_output - cost.review_output, False
    share = REWRITE_SHARE[h.score] if h.score is not None else 0.0
    net = h.changed_tokens - ESTIMATED_CALL_COST - round(h.changed_tokens * share)
    return net, True


def summarize(
    handoffs: list[Handoff],
    costs: dict[str, HandoffCost],
    now: datetime,
    days: int,
) -> list[Row]:
    cutoff = now - timedelta(days=days)
    groups: dict[tuple[str, str], list[Handoff]] = defaultdict(list)
    for h in handoffs:
        if h.ts >= cutoff:
            year, week, _ = h.ts.isocalendar()
            groups[(h.model, f"{year}-W{week:02d}")].append(h)

    rows = []
    for (model, week), group in sorted(groups.items()):
        results = [net_saved(h, costs.get(h.handoff_id)) for h in group]
        scored = [h.score for h in group if h.score is not None]
        avg = sum(scored) / len(scored) if scored else None
        redo = sum(s <= 2 for s in scored) / len(scored) if scored else None
        net = sum(r[0] for r in results)
        found = [costs.get(h.handoff_id) for h in group]
        measured = [c for c in found if c is not None and c.complete]
        rows.append(
            Row(
                model=model,
                week=week,
                handoffs=len(group),
                unscored=len(group) - len(scored),
                avg_score=avg,
                redo_rate=redo,
                local_tokens=sum(h.completion_tokens for h in group),
                net_output=net,
                new_input=(
                    sum(c.review_input - c.review_cached for c in measured)
                    if measured
                    else None
                ),
                cached_input=(
                    sum(c.review_cached for c in measured) if measured else None
                ),
                pct_estimated=sum(r[1] for r in results) / len(group),
                paying_off=net > 0 and (avg is None or avg >= 5),
            )
        )
    return rows


def format_rows(rows: list[Row], days: int) -> str:
    if not rows:
        return f"No handoffs in the last {days} days."
    header = (
        "model",
        "week",
        "handoffs",
        "avg score",
        "redo %",
        "local tok",
        "output saved",
        "new input",
        "cached input",
        "est %",
        "",
    )
    table = [header]
    for r in rows:
        table.append(
            (
                r.model,
                r.week,
                str(r.handoffs),
                "-" if r.avg_score is None else f"{r.avg_score:.1f}",
                "-" if r.redo_rate is None else f"{r.redo_rate:.0%}",
                str(r.local_tokens),
                str(r.net_output),
                "-" if r.new_input is None else str(r.new_input),
                "-" if r.cached_input is None else str(r.cached_input),
                f"{r.pct_estimated:.0%}",
                "" if r.paying_off else "NOT PAYING OFF",
            )
        )
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]
    lines = [
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
        for row in table
    ]
    return "\n".join(lines) + "\n\n" + VERDICT_NOTE
