"""One full triage run over the tickets in file order: guardrails, redaction, retries, validation, budget."""
import logging
import random
from dataclasses import dataclass

import pandas as pd

from instamart import config
from instamart.llm_backend import reset
from instamart.part_c import guardrails, redaction, validation
from instamart.part_c.llm_client import RetryLog, call_with_retry

log = logging.getLogger(__name__)

BUDGET_EXHAUSTED = "budget_exhausted"
CLASSIFIED = (validation.CLASSIFIED_JSON, validation.CLASSIFIED_KEYWORD)


@dataclass
class TriageRun:
    """Per-ticket results of one run plus its retry log and total token spend."""

    results: pd.DataFrame
    retry_log: RetryLog
    total_tokens: int
    model_calls: int


def build_messages(system_prompt: str, redacted_text: str) -> list[dict]:
    """System prompt plus a user message that is exactly the redacted ticket text."""
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": redacted_text}]


def run_triage(tickets: pd.DataFrame, system_prompt: str, token_budget: int | None = None) -> TriageRun:
    """Classify every ticket in file order; token_budget=None means no budget."""
    reset()                                             # immediately before each full run
    rng = random.Random(config.RETRY_SEED)
    retry_log, total_tokens, model_calls, rows = RetryLog(), 0, 0, []
    for ticket in tickets.itertuples(index=False):
        row = {"ticket_id": ticket.ticket_id, "customer_id": ticket.customer_id, "category": "", "tokens_used": 0}
        guard = guardrails.check_input(ticket.text)
        if guard:
            rows.append({**row, "status": guard})
            continue
        if token_budget is not None and total_tokens >= token_budget:
            rows.append({**row, "status": BUDGET_EXHAUSTED})
            continue
        redacted, _ = redaction.redact(ticket.text)
        response = call_with_retry(build_messages(system_prompt, redacted), ticket.ticket_id, rng, retry_log)
        model_calls += 1
        tokens = response.usage.total_tokens
        total_tokens += tokens
        status, category = validation.validate_reply(response.choices[0].message.content)
        rows.append({**row, "status": status, "category": category, "tokens_used": tokens})
    log.info("triage run: %d tickets, %d successful calls, %d retries, %d tokens",
             len(rows), model_calls, len(retry_log.entries), total_tokens)
    return TriageRun(pd.DataFrame(rows), retry_log, total_tokens, model_calls)


def summarise(run: TriageRun, tickets: pd.DataFrame) -> dict:
    """Classified count, accuracy over classified tickets, tokens and tokens per classified ticket."""
    merged = run.results.merge(tickets[["ticket_id", "true_category"]], on="ticket_id")
    classified = merged[merged["status"].isin(CLASSIFIED)]
    correct = int((classified["category"] == classified["true_category"]).sum())
    n = len(classified)
    return {
        "status_counts": run.results["status"].value_counts().to_dict(),
        "classified": n, "correct": correct,
        "accuracy_pct": round(100.0 * correct / n, 1) if n else 0.0,
        "total_tokens": run.total_tokens, "model_calls": run.model_calls,
        "tokens_per_classified": round(run.total_tokens / n, 1) if n else 0.0,
        "transient_errors": len(run.retry_log.entries),
    }


def confusion_table(run: TriageRun, tickets: pd.DataFrame) -> pd.DataFrame:
    """Rows = true category, columns = predicted category, over classified tickets only."""
    merged = run.results.merge(tickets[["ticket_id", "true_category"]], on="ticket_id")
    classified = merged[merged["status"].isin(CLASSIFIED)]
    table = pd.crosstab(classified["true_category"], classified["category"])
    return table.reindex(index=config.CATEGORIES, columns=config.CATEGORIES, fill_value=0)
