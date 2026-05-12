import pytest

from pedalpoint.error_classifier import classify_error


@pytest.mark.parametrize(
    "text,expected",
    [
        # auth_error — 401 and variants
        ("401 Unauthorized", "auth_error"),
        ("invalid api key", "auth_error"),
        ("unauthorized", "auth_error"),
        ("invalid_api_key provided", "auth_error"),
        # hard_quota — 402 and variants
        ("402 Payment Required", "hard_quota"),
        ("402 insufficient_quota", "hard_quota"),
        ("quota exceeded", "hard_quota"),
        ("billing hard limit reached", "hard_quota"),
        ("insufficient credits", "hard_quota"),
        ("You have exceeded your quota", "hard_quota"),
        # hard_quota — Claude Code upgrade-prompt variants
        ("Upgrade your plan to continue", "hard_quota"),
        ("You've reached your plan limit", "hard_quota"),
        ("You've reached your usage limit", "hard_quota"),
        ("Your usage limit has been reached", "hard_quota"),
        # rate_limit — 429 and variants
        ("429 Too Many Requests", "rate_limit"),
        ("rate limit exceeded", "rate_limit"),
        ("rate-limit", "rate_limit"),
        ("RateLimit hit", "rate_limit"),
        # overload — 529 and variants
        ("529 server overloaded", "overload"),
        ("The server is overloaded", "overload"),
        ("service capacity exceeded", "overload"),
        # network
        ("connection timeout", "network"),
        ("Connection refused", "network"),
        ("Read timeout", "network"),
        # rate_limit phrased with "reached" must NOT become hard_quota
        ("rate limit reached", "rate_limit"),
        ("rate-limit reached", "rate_limit"),
        # unknown
        ("some unrecognized error message", "unknown"),
        ("500 Internal Server Error", "unknown"),
    ],
)
def test_classify_error(text: str, expected: str) -> None:
    assert classify_error(text) == expected


def test_case_insensitive_quota() -> None:
    assert classify_error("QUOTA EXCEEDED") == "hard_quota"


def test_case_insensitive_rate_limit() -> None:
    assert classify_error("RATE LIMIT") == "rate_limit"


def test_hard_quota_takes_priority_over_rate_limit() -> None:
    # If a message somehow contains both, hard_quota wins (checked first)
    assert classify_error("402 rate limit quota") == "hard_quota"


def test_auth_error_takes_priority_over_hard_quota() -> None:
    # 401 in message should not be consumed by hard_quota pattern
    assert classify_error("401 quota exceeded") == "auth_error"
