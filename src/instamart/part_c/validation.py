"""Rule-based validation of every model reply; never guesses (task 5)."""
import json
import re

from instamart import config

CLASSIFIED_JSON = "classified_json"
CLASSIFIED_KEYWORD = "classified_keyword"
FLAGGED_INVALID = "flagged_invalid_output"


def validate_reply(text: str | None) -> tuple[str, str]:
    """Return (status, category); category is '' whenever the reply is flagged for human review."""
    try:
        parsed = json.loads(text or "")
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if parsed is not None:
        category = parsed.get("category") if isinstance(parsed, dict) else None
        return (CLASSIFIED_JSON, category) if category in config.CATEGORIES else (FLAGGED_INVALID, "")
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    found = [c for c in config.CATEGORIES if c in words]
    return (CLASSIFIED_KEYWORD, found[0]) if len(found) == 1 else (FLAGGED_INVALID, "")
