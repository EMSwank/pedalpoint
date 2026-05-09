import pytest
from pedalpoint.error_classifier import classify_error


@pytest.mark.parametrize("text,expected", [
    # hard_quota — 402 and variants
    ("402 Payment Required",            "hard_quota"),
    ("402 insufficient_quota",          "hard_quota"),
    ("quota exceeded",                  "hard_quota"),
    ("billing hard limit reached",      "hard_quota"),
    ("insufficient credits",            "hard_quota"),
    ("You have exceeded your quota",    "hard_quota"),
    # rate_limit — 429 and variants
    ("429 Too Many Requests",           "rate_limit"),
    ("rate limit exceeded",             "rate_limit"),
    ("rate-limit",                      "rate_limit"),
    ("RateLimit hit",                   "rate_limit"),
    # overload — 529 and variants
    ("529 server overloaded",           "overload"),
    ("The server is overloaded",        "overload"),
    ("service capacity exceeded",       "overload"),
    # network
    ("connection timeout",              "network"),
    ("Connection refused",              "network"),
    ("Read timeout",                    "network"),
    # unknown
    ("some unrecognized error message", "unknown"),
    ("500 Internal Server Error",       "unknown"),
])
def test_classify_error(text: str, expected: str) -> None:
    assert classify_error(text) == expected


def test_case_insensitive_quota() -> None:
    assert classify_error("QUOTA EXCEEDED") == "hard_quota"


def test_case_insensitive_rate_limit() -> None:
    assert classify_error("RATE LIMIT") == "rate_limit"


def test_hard_quota_takes_priority_over_rate_limit() -> None:
    # If a message somehow contains both, hard_quota wins (checked first)
    assert classify_error("402 rate limit quota") == "hard_quota"
