import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"401|unauthorized|invalid.{0,10}key", re.IGNORECASE), "auth_error"),
    (
        re.compile(
            r"402|quota|billing|insufficient"
            r"|upgrade.*plan|plan.*limit|usage.{0,20}limit|limit.*reached",
            re.IGNORECASE,
        ),
        "hard_quota",
    ),
    (re.compile(r"429|rate.?limit", re.IGNORECASE), "rate_limit"),
    (re.compile(r"529|overload|capacity", re.IGNORECASE), "overload"),
    (re.compile(r"timeout|connection", re.IGNORECASE), "network"),
]


def classify_error(text: str) -> str:
    """Return the error category for a given error message string."""
    for pattern, error_type in _PATTERNS:
        if pattern.search(text):
            return error_type
    return "unknown"
