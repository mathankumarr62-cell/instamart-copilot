"""Model calls wrapped in retries with exponential backoff and jitter (task 4)."""
import logging
import random
import time
from dataclasses import dataclass, field

from instamart import config
from instamart.llm_backend import TransientLLMError, chat
from instamart.part_c.redaction import assert_no_pii

log = logging.getLogger(__name__)


@dataclass
class RetryLog:
    """Every retry made during one run: (ticket_id, retry_number, wait_seconds)."""

    entries: list[tuple[str, int, float]] = field(default_factory=list)


def backoff_wait(retry_number: int, rng: random.Random) -> float:
    """Wait before retry n: BASE_DELAY * 2**n * uniform(0.9, 1.15)."""
    return config.BASE_DELAY * 2 ** retry_number * rng.uniform(*config.JITTER_RANGE)


def call_with_retry(messages: list[dict], ticket_id: str, rng: random.Random, retry_log: RetryLog,
                    max_retries: int = config.MAX_RETRIES):
    """Call the model, retrying TransientLLMError up to max_retries times; re-raise if all retries fail."""
    for retry_number in range(max_retries + 1):
        assert_no_pii(messages)
        try:
            return chat(messages)
        except TransientLLMError as exc:
            if retry_number == max_retries:
                raise
            wait = backoff_wait(retry_number, rng)
            retry_log.entries.append((ticket_id, retry_number, wait))
            log.info("retry ticket=%s retry=%d wait=%.4fs after %s", ticket_id, retry_number, wait, exc)
            time.sleep(wait)
    raise AssertionError("unreachable")
