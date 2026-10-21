"""PII redaction with the brief's three patterns, applied in a fixed order (task 2)."""
import re

# Order matters: emails first, so digits inside an address are never read as a phone number.
PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    ("phone", re.compile(r"\b[6-9]\d{9}\b"), "[PHONE]"),
    ("order_id", re.compile(r"ORD-\d{6}"), "[ORDER_ID]"),
]


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace emails, phones and order ids in order; return the redacted text and per-type counts."""
    counts = {}
    for name, pattern, placeholder in PATTERNS:
        text, n = pattern.subn(placeholder, text)
        counts[name] = n
    return text, counts


def find_pii(text: str) -> list[str]:
    """Return every substring that any of the three patterns still matches (empty when clean)."""
    return [m.group(0) for _, pattern, _ in PATTERNS for m in pattern.finditer(text or "")]


def assert_no_pii(messages: list[dict]) -> None:
    """Fail loudly if any message about to be sent to the model still contains PII."""
    for message in messages:
        leaked = find_pii(message.get("content") or "")
        assert not leaked, f"PII would reach the model: {leaked}"
