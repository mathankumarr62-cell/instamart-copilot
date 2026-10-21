"""Input guardrails applied before any model call (task 1)."""
from instamart import config
from instamart.llm_backend import est_tokens

SKIPPED_EMPTY = "skipped_empty"
FLAGGED_LONG = "flagged_long"


def check_input(text: str, max_tokens: int = config.MAX_INPUT_TOKENS) -> str | None:
    """Return skipped_empty / flagged_long when the ticket must not reach the model, else None."""
    if not text or not text.strip():
        return SKIPPED_EMPTY
    if est_tokens(text) > max_tokens:
        return FLAGGED_LONG
    return None
