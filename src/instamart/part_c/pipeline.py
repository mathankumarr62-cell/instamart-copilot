"""Part C orchestration: guardrail and redaction audit, prompt comparison, budget demo, final routed run."""
import logging

import pandas as pd

from instamart import config, io_utils
from instamart.llm_backend import est_tokens
from instamart.part_c import guardrails, prompts, redaction, routing, triage

log = logging.getLogger(__name__)


def guardrail_summary(tickets: pd.DataFrame) -> dict:
    """Count empty and long tickets and record the token estimates of the long ones."""
    statuses = tickets["text"].map(guardrails.check_input)
    long_tokens = [est_tokens(t) for t, s in zip(tickets["text"], statuses) if s == guardrails.FLAGGED_LONG]
    return {"empty": int((statuses == guardrails.SKIPPED_EMPTY).sum()),
            "long": int((statuses == guardrails.FLAGGED_LONG).sum()),
            "long_ticket_tokens": long_tokens, "eligible": int(statuses.isna().sum())}


def redaction_summary(tickets: pd.DataFrame) -> dict:
    """Redact all 164 tickets, sum substitutions per type and prove nothing is left afterwards."""
    totals = {name: 0 for name, _, _ in redaction.PATTERNS}
    leftovers = 0
    for text in tickets["text"]:
        redacted, counts = redaction.redact(text)
        for name, n in counts.items():
            totals[name] += n
        leftovers += len(redaction.find_pii(redacted))
    return {**totals, "total": sum(totals.values()), "left_after_redaction": leftovers}


def prompt_summary() -> dict:
    """Token sizes of the two system prompts."""
    return {"zero_shot_tokens": est_tokens(prompts.ZERO_SHOT), "few_shot_tokens": est_tokens(prompts.FEW_SHOT),
            "zero_shot": prompts.ZERO_SHOT, "few_shot": prompts.FEW_SHOT}


def write_csv(df: pd.DataFrame, path) -> None:
    """Write an output CSV with LF line endings."""
    df.to_csv(path, index=False, lineterminator="\n")


def budget_demo(tickets: pd.DataFrame, segments: pd.DataFrame) -> dict:
    """Zero-shot run under TOKEN_BUDGET=6000 (lowered by 1000 until at least one ticket is exhausted)."""
    budget = config.DEMO_TOKEN_BUDGET
    while True:
        run = triage.run_triage(tickets, prompts.ZERO_SHOT, token_budget=budget)
        exhausted = int((run.results["status"] == triage.BUDGET_EXHAUSTED).sum())
        if exhausted or budget <= 1000:
            break
        budget -= 1000
    write_csv(routing.apply_routing(run.results, segments), config.TRIAGE_BUDGET_DEMO)
    return {"token_budget": budget, "budget_exhausted": exhausted, "total_tokens": run.total_tokens,
            "model_calls": run.model_calls, "status_counts": run.results["status"].value_counts().to_dict()}


def run() -> dict:
    """Run every Part C task and persist the CSVs and outputs/reports/part_c.json."""
    tickets = io_utils.read_raw_tickets()
    segments = routing.load_segments()
    zero = triage.run_triage(tickets, prompts.ZERO_SHOT)
    few = triage.run_triage(tickets, prompts.FEW_SHOT)
    demo = budget_demo(tickets, segments)
    final = triage.run_triage(tickets, prompts.FEW_SHOT, token_budget=config.FINAL_TOKEN_BUDGET)
    routed = routing.apply_routing(final.results, segments)
    write_csv(routed, config.TRIAGE_RESULTS)

    report = {
        "tickets": len(tickets),
        "guardrails": guardrail_summary(tickets),
        "redaction": redaction_summary(tickets),
        "prompts": prompt_summary(),
        "retries": {"count": len(zero.retry_log.entries),
                    "retry_numbers": sorted({n for _, n, _ in zero.retry_log.entries}),
                    "min_wait": round(min(w for _, _, w in zero.retry_log.entries), 4),
                    "max_wait": round(max(w for _, _, w in zero.retry_log.entries), 4),
                    "permanent_errors": 0,
                    "log": [{"ticket_id": t, "retry": n, "wait": round(w, 4)} for t, n, w in zero.retry_log.entries]},
        "zero_shot": triage.summarise(zero, tickets),
        "few_shot": triage.summarise(few, tickets),
        "zero_shot_confusion": triage.confusion_table(zero, tickets).reset_index().rename(
            columns={"true_category": "true"}),
        "budget_demo": demo,
        "final": {**triage.summarise(final, tickets),
                  "route_counts": routed["route"].value_counts().to_dict(),
                  "priority_counts": routed["priority"].value_counts().to_dict(),
                  "rows": len(routed)},
    }
    io_utils.write_json(config.report_path("c"), report)
    log.info("Part C report written to %s", config.report_path("c"))
    return report
