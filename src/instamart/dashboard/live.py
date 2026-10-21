"""Live demos for the dashboard, using the real Part C / Part D functions and mock_llm.

The triage and policy demos write nothing. The agent demo runs with its ledger and checkpoints redirected
to state/demo/, so outputs/refund_ledger.jsonl, outputs/agent_runs.jsonl and state/*.json are never touched."""
import itertools
import json
import random
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone

from instamart import config
from instamart.dashboard.data import STATE_LOCK
from instamart.llm_backend import est_tokens
from instamart.part_c import guardrails, prompts, redaction, routing, triage, validation
from instamart.part_c.llm_client import RetryLog, call_with_retry
from instamart.part_d import agent, rag, tools
from instamart.part_d.retrieval import get_index

PROMPTS = {"few_shot": prompts.FEW_SHOT, "zero_shot": prompts.ZERO_SHOT}
DEMO_CHECKPOINTS = config.DEMO_DIR / "checkpoints"
_run_counter = itertools.count(1)


def _segment(customer_id: str | None) -> dict | None:
    """Segment row of a customer from Part B's customer_segments.csv, or None."""
    if not customer_id:
        return None
    seg = routing.load_segments()
    match = seg[seg["customer_id"] == customer_id]
    return None if match.empty else {"segment_name": match.iloc[0]["segment_name"],
                                     "is_premium": bool(match.iloc[0]["is_premium"])}


def try_ticket(text: str, prompt: str = "few_shot", customer_id: str | None = None) -> dict:
    """Run one ticket through guardrail -> redaction -> model (with retries) -> validation -> routing."""
    guard = guardrails.check_input(text)
    redacted, counts = redaction.redact(text)
    result = {"original": text, "estimated_tokens": est_tokens(text), "guardrail": guard or "passed",
              "redacted": redacted, "redaction_counts": counts, "pii_left": len(redaction.find_pii(redacted)),
              "prompt": prompt, "sent_to_model": guard is None, "reply": None, "tokens_used": 0, "retries": [],
              "status": guard, "category": ""}
    if guard is None:
        retry_log = RetryLog()
        with STATE_LOCK:                                  # mock_llm keeps process-wide call counters
            response = call_with_retry(triage.build_messages(PROMPTS[prompt], redacted), "dashboard",
                                       random.Random(config.RETRY_SEED), retry_log)
        reply = response.choices[0].message.content
        status, category = validation.validate_reply(reply)
        result.update(reply=reply, tokens_used=response.usage.total_tokens, status=status, category=category,
                      retries=[{"retry": n, "wait_seconds": round(w, 4)} for _, n, w in retry_log.entries])
    segment = _segment(customer_id)
    route, priority = routing.route(result["status"], result["category"], bool(segment and segment["is_premium"]))
    return {**result, "customer_id": customer_id, "segment": segment, "route": route, "priority": priority}


def ask_policy(question: str) -> dict:
    """Grounded answer from the real RAG pipeline plus the three retrieved chunks and their cosine scores."""
    chunks = get_index().retrieve(question, config.TOP_K)
    result = rag.answer(question)
    return {"question": question, "answer": result["answer"],
            "grounded": not result["answer"].startswith(rag.FALLBACK_PREFIX), "sources": chunks}


@contextmanager
def demo_sandbox():
    """Point the agent's ledger and checkpoints at state/demo/ for the duration of one demo run."""
    with STATE_LOCK:
        saved = (config.STATE_DIR, tools.LEDGER_PATH)
        DEMO_CHECKPOINTS.mkdir(parents=True, exist_ok=True)
        config.STATE_DIR, tools.LEDGER_PATH = DEMO_CHECKPOINTS, config.DEMO_LEDGER
        try:
            yield
        finally:
            config.STATE_DIR, tools.LEDGER_PATH = saved


def demo_ledger() -> list[dict]:
    """Lines of the demo ledger (state/demo/refund_ledger.jsonl)."""
    if not config.DEMO_LEDGER.exists():
        return []
    return [json.loads(line) for line in config.DEMO_LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_agent_demo(message: str, customer_id: str | None = None, max_iterations: int = config.AGENT_MAX_ITERATIONS,
                   token_limit: int = config.AGENT_TOKEN_LIMIT) -> dict:
    """Run the real ReAct agent in the demo sandbox and return its full step trace."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    run_id = f"demo_{stamp}_{next(_run_counter)}"
    with demo_sandbox():
        result = agent.run_agent(message, scenario_id="dashboard", max_iterations=max_iterations,
                                 token_limit=token_limit, run_id=run_id)
    return {**result, "customer_id": customer_id, "limits": {"max_iterations": max_iterations,
                                                           "token_limit": token_limit,
                                                           "time_limit_seconds": config.AGENT_TIME_LIMIT_SECONDS},
            "ledger": "state/demo/refund_ledger.jsonl", "demo_ledger": demo_ledger()}


def reset_demo() -> dict:
    """Delete the demo sandbox (state/demo/) so the next demo refund is issued afresh."""
    with STATE_LOCK:
        if config.DEMO_DIR.exists():
            shutil.rmtree(config.DEMO_DIR)
    return {"reset": True, "demo_ledger": []}
