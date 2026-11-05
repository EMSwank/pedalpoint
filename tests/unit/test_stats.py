from datetime import UTC, datetime, timedelta

from pedalpoint.stats import (
    ESTIMATED_CALL_COST,
    REWRITE_SHARE,
    Handoff,
    Row,
    format_rows,
    join_records,
    net_saved,
    summarize,
)
from pedalpoint.transcripts import HandoffCost

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)  # ISO week 2026-W44


def _h(hid="a", score=7, changed=500, model="m1", days_ago=0, completion=600):
    return Handoff(
        handoff_id=hid,
        ts=NOW - timedelta(days=days_ago),
        model=model,
        backend="mlx",
        completion_tokens=completion,
        changed_tokens=changed,
        score=score,
    )


def test_constants():
    assert ESTIMATED_CALL_COST == 100
    assert REWRITE_SHARE == {7: 0.0, 6: 0.1, 5: 0.3, 4: 0.5, 3: 0.75, 2: 0.9, 1: 1.0}


def test_net_saved_measured():
    assert net_saved(_h(), HandoffCost(80, 120, 4000, True)) == (300, False)


def test_net_saved_estimated_score_6():
    assert net_saved(_h(score=6), None) == (350, True)


def test_net_saved_score_1_negative():
    assert net_saved(_h(score=1), None) == (-100, True)


def test_net_saved_unscored_estimate():
    assert net_saved(_h(score=None), None) == (400, True)


def test_net_saved_incomplete_cost_falls_back():
    assert net_saved(_h(score=6), HandoffCost(80, 10, 5, False)) == (350, True)


def _call(hid, ts="2026-10-28T10:00:00+00:00", model="m1"):
    return {
        "kind": "call",
        "handoff_id": hid,
        "ts": ts,
        "model": model,
        "backend": "mlx",
        "completion_tokens": 600,
        "changed_tokens": 500,
    }


def _outcome(hid, score):
    return {"kind": "outcome", "handoff_id": hid, "score": score, "ts": "x"}


def test_join_records_latest_outcome_wins():
    handoffs = join_records([_call("a"), _outcome("a", 3), _outcome("a", 6)])
    assert len(handoffs) == 1
    assert handoffs[0].score == 6
    assert handoffs[0].ts == datetime(2026, 10, 28, 10, tzinfo=UTC)


def test_join_records_orphan_outcome_ignored():
    handoffs = join_records([_outcome("x", 7), _call("a")])
    assert [h.handoff_id for h in handoffs] == ["a"]
    assert handoffs[0].score is None


def test_join_records_skips_malformed_call():
    assert join_records([{"kind": "call", "handoff_id": "a"}]) == []


def test_summarize_groups_by_model_and_week():
    rows = summarize(
        [_h("a"), _h("b"), _h("c", model="m2"), _h("d", days_ago=7)],
        {},
        NOW,
        days=14,
    )
    keys = [(r.model, r.week, r.handoffs) for r in rows]
    assert keys == [("m1", "2026-W43", 1), ("m1", "2026-W44", 2), ("m2", "2026-W44", 1)]


def test_summarize_filters_by_days():
    rows = summarize([_h("a"), _h("old", days_ago=30)], {}, NOW, days=7)
    assert sum(r.handoffs for r in rows) == 1


def test_summarize_row_values():
    rows = summarize(
        [_h("a", score=7), _h("b", score=2), _h("c", score=None)],
        {"a": HandoffCost(80, 20, 1000, True)},
        NOW,
        days=7,
    )
    row = rows[0]
    assert row == Row(
        model="m1",
        week="2026-W44",
        handoffs=3,
        unscored=1,
        avg_score=4.5,
        redo_rate=0.5,
        local_tokens=1800,
        net_output=400 + (500 - 100 - 450) + 400,
        new_input=1000,
        cached_input=0,
        pct_estimated=2 / 3,
        paying_off=False,
    )


def test_summarize_flags_negative_net():
    rows = summarize([_h("a", score=1)], {}, NOW, days=7)
    assert rows[0].paying_off is False


def test_summarize_paying_off():
    rows = summarize([_h("a", score=7)], {}, NOW, days=7)
    assert rows[0].paying_off is True


def test_summarize_all_unscored():
    rows = summarize([_h("a", score=None)], {}, NOW, days=7)
    assert rows[0].avg_score is None and rows[0].redo_rate is None
    assert rows[0].paying_off is True


def test_format_rows_empty():
    assert format_rows([], 7) == "No handoffs in the last 7 days."


def test_format_rows_marks_not_paying_off():
    rows = summarize([_h("a", score=7), _h("b", model="m2", score=1)], {}, NOW, 7)
    text = format_rows(rows, 7)
    lines = text.splitlines()
    assert "model" in lines[0] and "output saved" in lines[0]
    m1 = next(line for line in lines if line.startswith("m1"))
    m2 = next(line for line in lines if line.startswith("m2"))
    assert "NOT PAYING OFF" not in m1
    assert "NOT PAYING OFF" in m2


def test_summarize_splits_new_and_cached_input():
    row = summarize(
        [_h("a")], {"a": HandoffCost(80, 20, 1000, True, review_cached=900)}, NOW, 7
    )[0]
    assert (row.new_input, row.cached_input) == (100, 900)


def test_summarize_input_unknown_when_all_estimated():
    row = summarize([_h("a")], {}, NOW, 7)[0]
    assert (row.new_input, row.cached_input) == (None, None)


def test_summarize_input_counts_measured_handoffs_only():
    costs = {"a": HandoffCost(80, 20, 1000, True, review_cached=400)}
    row = summarize([_h("a"), _h("b")], costs, NOW, 7)[0]
    assert (row.new_input, row.cached_input) == (600, 400)
    assert row.pct_estimated == 0.5


def test_format_rows_shows_input_side_by_side():
    costs = {"a": HandoffCost(80, 20, 1000, True, review_cached=900)}
    lines = format_rows(summarize([_h("a")], costs, NOW, 7), 7).splitlines()
    assert "output saved" in lines[0]
    assert "new input" in lines[0] and "cached input" in lines[0]
    assert "100" in lines[1].split() and "900" in lines[1].split()


def test_format_rows_unknown_input_is_a_dash_not_zero():
    lines = format_rows(summarize([_h("a")], {}, NOW, 7), 7).splitlines()
    assert lines[1].split().count("-") == 2


def test_format_rows_says_what_the_verdict_covers():
    text = format_rows(summarize([_h("a")], {}, NOW, 7), 7)
    assert "output tokens and scores only" in text
    assert "cached input" in text.splitlines()[-1]
